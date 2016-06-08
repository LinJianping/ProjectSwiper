#encoding:utf-8
"""
ECG classification with Random Forest
Author : Gaopengfei
"""
import os
import sys
import json
import math
import pickle
import random
import time
import pdb
from multiprocessing.dummy import Pool as ThreadPool
from multiprocessing import Pool

import numpy as np
## machine learning methods
from sklearn.ensemble import RandomForestClassifier
import matplotlib.pyplot as plt

# project homepath
# 
curfilepath =  os.path.realpath(__file__)
curfolderpath = os.path.dirname(curfilepath)
projhomepath = curfolderpath
projhomepath = os.path.dirname(projhomepath)
# configure file
# conf is a dict containing keys
with open(os.path.join(projhomepath,'ECGconf.json'),'r') as fin:
    conf = json.load(fin)
sys.path.append(projhomepath)
#
# my project components
import extractfeature.extractfeature as extfeature
import extractfeature.randomrelations as RandRelation
import WTdenoise.wtdenoise as wtdenoise
import QTdata.loadQTdata as QTdb
from MatlabPloter.Result2Mat_Format import reslist_to_mat

## Main Scripts
# ==========
EPS = 1e-6

def show_drawing(folderpath = os.path.join(\
        os.path.dirname(curfilepath),'..','QTdata','QTdata_repo')):
    with open(os.path.join(folderpath,'sel103.txt'),'r') as fin:
        sig = pickle.load(fin)
    # sig with 'sig','time'and 'marks'
    ECGfv = extfeature.ECGfeatures(sig['sig'])
    fv = ECGfv.frompos(3e3)

def valid_signal_value(sig):
    # check Nan!
    # check Inf!
    float_inf = float('Inf')
    float_nan = float('Nan')
    if float_inf in sig or float_nan in sig:
        return False
    return True
def timing_for(function_handle,params,prompt = 'timing is',time_cost_output = None):
    time0 = time.time()
    ret = function_handle(*params)
    time1 = time.time()
    info_str = '{} [time cost {} s]'.format(prompt,time1-time0)
    print info_str
    # output
    if time_cost_output is not None and isinstance(time_cost_output,list):
        time_cost_output.append(time1-time0) 
    # return value
    return ret

# train and test
class ECGrf:
    def __init__(self,MAX_PARA_CORE = 6,SaveTrainingSampleFolder = None):
        # only test on areas with expert labels
        self.TestRange = 'Partial'# or 'All'
        # Parallel
        self.QTloader = QTdb.QTloader()
        self.mdl = None
        self.MAX_PARA_CORE = MAX_PARA_CORE
        # maximum samples for bucket testing
        self.MaxTestSample = 200
        # save training samples folder
        if SaveTrainingSampleFolder is None:
            ResultFolder = projhomepath
            ResultFolder_conf = conf['ResultFolder_Relative']
            for folder in ResultFolder_conf:
                ResultFolder = os.path.join(ResultFolder,folder)
            self.SaveTrainingSampleFolder = ResultFolder
        else:
            self.SaveTrainingSampleFolder = SaveTrainingSampleFolder
    @ staticmethod
    def RefreshRandomFeatureJsonFile(copyTo = None):
        # refresh random relations
        RandRelation.refresh_project_random_relations_computeLen(copyTo = copyTo)


    # label proc & convert to feature
    @staticmethod
    def collectfeaturesforsig(sig,SaveTrainingSampleFolder,blankrangelist = None,recID = None):
        #
        # parameters:
        # blankrangelist : [[l,r],...]
        #
        # collect training features from sig
        #
        # init
        Extractor = extfeature.ECGfeatures(sig['sig'])
        negposlist = []
        posposlist = [] # positive position list
        labellist = [] # positive label list
        tarpos = []
        trainingX,trainingy = [],[]
        # get Expert labels
        QTloader = QTdb.QTloader()
        # =======================================================
        # modified negposlist inside function
        # =======================================================
        ExpertLabels = QTloader.getexpertlabeltuple(None,sigIN = sig,negposlist = negposlist)
        posposlist,labellist = zip(*ExpertLabels)

        # ===============================
        # convert feature & append to X,y
        # Using Map build in function
        # ===============================
        FV = map(Extractor.frompos,posposlist)
        # append to trainging vector
        trainingX.extend(FV)
        trainingy.extend(labellist)
        
        # add neg samples
        Nneg = int(len(negposlist)*conf['negsampleratio'])
        #print 'Total number of negposlist =',len(negposlist)
        #print '-- Number of Training samples -- '
        #print 'Num of pos samples:',len(trainingX)
        #print 'Num of neg samples:',Nneg

        # if Number of Neg>0 then add negtive samples
        if len(negposlist) == 0 or Nneg<=0:
            print '[In function collect feature] Warning: negtive sample position list length is 0.'
        else:
            # collect negtive sample features
            #
            # leave blank for area without labels
            #
            negposset = set(negposlist)
            if blankrangelist is not None:
                blklist = []
                for pair in blankrangelist:
                    blklist.extend(range(pair[0],pair[1]+1))
                blkset = set(blklist)
                negposset -= blkset
                
            selnegposlist = random.sample(negposset,Nneg)
            time_neg0 = time.time()
            negFv = map(Extractor.frompos,selnegposlist)
            trainingX.extend(negFv)
            trainingy.extend(['white']*Nneg)
            print '\nTime for collect negtive samples:{:.2f}s'.format(time.time() - time_neg0)
        # =========================================
        # Save sample list
        # =========================================
        ResultFolder = os.path.join(SaveTrainingSampleFolder,'TrainingSamples')
        # mkdir if not exists
        if os.path.exists(ResultFolder) == False:
            os.mkdir(ResultFolder)
        # -----
        # sample_list
        # [(pos,label),...]
        # -----
        sample_list = zip(selnegposlist,len(selnegposlist)*['white'])
        sample_list.extend(ExpertLabels)
        if recID is not None:
            # save recID sample list
            with open(os.path.join(ResultFolder,recID+'.pkl'),'w') as fout:
                pickle.dump(sample_list,fout)
            save_mat_filename = os.path.join(ResultFolder,recID+'.mat')
            reslist_to_mat(sample_list,mat_filename = save_mat_filename)
        return (trainingX,trainingy) 
        
    def CollectRecFeature(self,recname):
        print 'Parallel Collect RecFeature from {}'.format(recname)
        # load blank area list
        blkArea = conf['labelblankrange']
        ## debug log:
        debugLogger.dump('collecting feature for {}\n'.format(recname))
        # load sig
        QTloader = QTdb.QTloader()
        sig = QTloader.load(recname)
        if valid_signal_value(sig['sig']) == False:
            return [[],[]]
        # blank list
        blklist = None
        if recname in blkArea:
            print recname,'in blank Area list.'
            blklist = blkArea[recname]
        tX,ty = ECGrf.collectfeaturesforsig(sig,SaveTrainingSampleFolder = self.SaveTrainingSampleFolder,blankrangelist = blklist,recID = recname)
        return (tX,ty)

    def training(self,reclist):
        # training feature vector
        trainingX = []
        trainingy = []

        # Parallel
        # Multi Process
        #pool = Pool(self.MAX_PARA_CORE)
        pool = Pool(2)

        # train with reclist
        # map function (recname) -> (tx,ty)

        #trainingTuples = timing_for(pool.map,[Parallel_CollectRecFeature,reclist],prompt = 'All records collect feature time')
        # single core:
        trainingTuples = timing_for(map,[self.CollectRecFeature,reclist],prompt = 'All records collect feature time')
        # close pool
        pool.close()
        pool.join()
        # organize features
        tXlist,tylist = zip(*trainingTuples)
        map(trainingX.extend,tXlist)
        map(trainingy.extend,tylist)

        # train Random Forest Classifier
        Tree_Max_Depth = conf['Tree_Max_Depth']
        RF_TreeNumber = conf['RF_TreeNumber']
        rfclassifier = RandomForestClassifier(n_estimators = RF_TreeNumber,max_depth = Tree_Max_Depth,n_jobs =4,warm_start = False)
        print 'Random Forest Training Sample Size : [{} samples x {} features]'.format(len(trainingX),len(trainingX[0]))
        timing_for(rfclassifier.fit,(trainingX,trainingy),prompt = 'Random Forest Fitting')
        # save&return classifier model
        self.mdl = rfclassifier
        return rfclassifier
    
    def test_signal(self,signal,rfmdl = None,MultiProcess = 'off'):
        # test rawsignal
        if rfmdl is None:
            rfmdl = self.mdl
        # Extracting Feature
        if MultiProcess == 'off':
            FeatureExtractor = extfeature.ECGfeatures(signal)
        else:
            raise StandardError('MultiProcess on is not defined yet!')
        # testing
        if MultiProcess == 'on':
            raise StandardError('MultiProcess on is not defined yet!')
        elif MultiProcess == 'off':
            record_predict_result = self.test_with_positionlist(rfmdl,range(0,len(signal)),FeatureExtractor)
        return record_predict_result

    # testing ECG record with trained mdl
    def testing(self,reclist,rfmdl = None,saveresultfolder = None):
        #
        # default parameter
        #
        if rfmdl is None:
            rfmdl = self.mdl

        # test all files in reclist
        PrdRes = []
        for recname in reclist:
            time_rec0 = time.time()
            sig = self.QTloader.load(recname)
            FeatureExtractor = extfeature.ECGfeatures(sig['sig'])
            # original rawsig
            rawsig = sig['sig']
            N_signal = len(rawsig)
            # init
            prRes = []
            testSamples = []
            #
            # get prRange:
            if conf['QTtest'] == 'FastTest':
                TestRegionFolder = r'F:\LabGit\ECG_RSWT\TestSchemes\QT_TestRegions'
                with open(os.path.join(TestRegionFolder,'{}_TestRegions.pkl'.format(recname)),'r') as fin:
                    TestRegions = pickle.load(fin)
                prRange = []
                for region in TestRegions:
                    prRange.extend(range(region[0],region[1]+1))
            
            debugLogger.dump('Testing samples with lenth {}:[{},{}]\n'.format(len(prRange),prRange[0],prRange[-1]))
            #
            # pickle dumple modle to file for multi process testing
            #
            record_predict_result = self.\
                    test_with_positionlist(\
                        rfmdl,\
                        prRange,\
                        FeatureExtractor\
                    )

            #
            # prediction result for each record            
            #
            PrdRes.append((recname,record_predict_result))
            
            # end testing time
            time_rec1 = time.time()
            print 'Testing time for record {} is {:.2f} s'.format(recname,time_rec1-time_rec0)
            debugLogger.dump('Testing time for record {} is {:.2f} s\n'.format(recname,time_rec1-time_rec0))

        # save Prediction Result
        if saveresultfolder is not None:
            # save results
            saveresult_filename = os.path.join(saveresultfolder,'result_{}'.format(recname))
            with open(saveresult_filename,'w') as fout:
                # No detection
                if PrdRes is None or len(PrdRes) == 0:
                    warn_msg = u'本次测试没有检测到特征点。Test Records:\n{}'.format(reclist)
                    print warn_msg
                    debugLogger.dump(warn_msg)
                    recres = (recname,[])
                else:
                    recres = PrdRes[0]
                pickle.dump(recres ,fout)
                print 'saved prediction result to {}'.format(saveresult_filename)
        return PrdRes

    def test_with_positionlist(self,rfmdl,poslist,featureextractor):
        # test with buckets
        # 
        # Prediction Result
        # [(pos,label)...]
        PrdRes = []
        # prediction probability
        PrdProb = []

        # testing & show progress
        Ntest = self.MaxTestSample
        Lposlist = len(poslist)
        Nbuckets = int(Lposlist/Ntest)
        if Nbuckets * Ntest < Lposlist:
            Nbuckets += 1
        for i in range(0,Nbuckets):
            # progress bar
            sys.stdout.write('\rTesting: {:02}buckets left.'.format(Nbuckets - i -1))
            sys.stdout.flush()

            # get each bucket's range
            #
            index_L = i*Ntest
            index_R = (i+1)*Ntest
            index_R = min(index_R,Lposlist)
            samples_tobe_tested = map(featureextractor.frompos,poslist[index_L:index_R])
            # predict
            #
            res = rfmdl.predict(samples_tobe_tested)
            mean_prob = rfmdl.predict(samples_tobe_tested)
            print 'probability shape:',mean_prob.shape
            print 'mean probability:',mean_prob
            print 'array of classes:',rfmdl.classes_
            # sample to make sure
            n_debug = 3
            print 'first {} result is :',res[0:n_debug]
            print 'predict probability is :',mean_prob[0:n_debug,:]
            pdb.set_trace()
            PrdRes.extend(res.tolist())
            # PrdProb.extend(res[
            
            
        if len(PrdRes) != len(poslist):
            print 'len(prd Results) = ',len(PrdRes),'Len(poslist) = ',len(poslist)
            print 'PrdRes:'
            print PrdRes
            print 'poslist:'
            print poslist
            pdb.set_trace()
            raise StandardError('test Error: output label length doesn''t match!')
        return zip(poslist,PrdRes,PrdProb)

    def plotresult(\
            self,\
            prdResult_rec,\
            figureID = 1,\
            showExpertLabel = False):
#
        # parameter check
        if len(prdResult_rec)!=2:
            raise StandardError('\
                    input prdRes must be of form\
                    (recname,recResult)!')
        ## plot signal waveform & labels
        recname,recRes = prdResult_rec

        plt.figure(figureID);
        sig = self.QTloader.load(recname)
        rawsig = sig['sig']
        # plot sig 
        plt.plot(rawsig)
        # plot prd indexes
        #raw_input('input sth...')
        for prdpair in recRes:
            label = prdpair[1]
            pos = prdpair[0]
            mker = 'kh'

            if label == 'T':
                mker = 'ro'
            elif label == 'R':
                mker = 'go'
            elif label == 'P':
                mker = 'bo'
            elif label == 'Tonset':
                mker = 'r<'
            elif label == 'Toffset':
                mker = 'r>'
            elif label == 'Ronset':
                mker = 'g<'
            elif label == 'Roffset':
                mker = 'g>'
            elif label == 'Ponset':
                mker = 'b<'
            elif label == 'Poffset':
                mker = 'b>'
            else:# white
                mker = 'w.'
            plt.plot(pos,rawsig[pos],mker)
        # plot expert marks
        if showExpertLabel:
            # blend together
            explbpos = self.QTloader.getexpertlabeltuple(recname)
            explbpos = [x[0] for x in explbpos]
            explbAmp = [rawsig[x] for x in explbpos]
            # plot expert labels
            h_expertlabel = plt.plot(\
                    explbpos,explbAmp,'rx')
            # set plot properties
            plt.setp(h_expertlabel,'ms',12)

        plt.title(recname)
        #plt.xlim((145200,151200))
        plt.show()

    def plot_testing_result(self,RecResults,figureID = 1):
        for recname,recRes in RecResults:
            print recRes
            raw_input('recRes...')
            #recname = rec

            plt.figure(figureID);
            sig = self.QTloader.load(recname)
            rawsig = sig['sig']
            # plot sig 
            plt.plot(rawsig)
            # plot prd indexes
            #raw_input('input sth...')
            for prdpair in recRes:
                label = prdpair[1]
                pos = prdpair[0]
                mker = 'kh'

                if label == 'T':
                    mker = 'ro'
                elif label == 'R':
                    mker = 'go'
                elif label == 'P':
                    mker = 'bo'
                elif label == 'Tonset':
                    mker = 'r<'
                elif label == 'Toffset':
                    mker = 'r>'
                elif label == 'Ronset':
                    mker = 'g<'
                elif label == 'Roffset':
                    mker = 'g>'
                elif label == 'Ponset':
                    mker = 'b<'
                elif label == 'Poffset':
                    mker = 'b>'
                else:# white
                    mker = 'w.'
                plt.plot(pos,rawsig[pos],mker)
            plt.title(recname)
            #plt.xlim((145200,151200))
            plt.show()
        
    def testmdl(\
                self,\
                reclist = ['sel103',],\
                mdl = None,\
                TestResultFileName = None\
            ):
        # default parameter
        if mdl is None:
            mdl = self.mdl

        # testing
        RecResults = self.testing(reclist)
        #
        # save to model file 
        if TestResultFileName is not None:
            filename_saveresult = TestResultFileName
        else:
            filename_saveresult = os.path.join(\
                    curfolderpath,\
                    'testresult{}.out'.format(\
                    int(time.time())))

            # warning :save to default folder
            print '**Warning: save result to {}'.format(filename_saveresult)
            debugLogger.dump('**Warning: save result to {}'.format(filename_saveresult))

        with open(filename_saveresult,'w') as fout:
            pickle.dump(RecResults ,fout)
            print 'saved prediction result to {}'.\
                    format(filename_saveresult)
    def testrecords(self,saveresultfolder,reclist = ['sel103',],mdl = None,TestResultFileName = None):
        # default parameter
        if mdl is None:
            mdl = self.mdl
        #saveresultfolder = os.path.dirname(filename_saveresult)
        for recname in reclist:
            # testing
            RecResults = self.testing([recname,],saveresultfolder = saveresultfolder)
        

# =======================
## debug Logger
# =======================
class debugLogger():
    def __init__(self):
        pass
    @staticmethod
    def dump(text):
        loggerpath = os.path.join(\
                projhomepath,\
                'classification_process.log')
        with open(loggerpath,'a') as fin:
            fin.write(text)
    @staticmethod
    def clear():
        loggerpath = os.path.join(\
                projhomepath,\
                'classification_process.log')
        fp = open(loggerpath,'w')
        fp.close()

# ======================================
# Parallelly Collect training sample for each rec
# ======================================
def Parallel_CollectRecFeature(recname):
    print 'Parallel Collect RecFeature from {}'.format(recname)
    # load blank area list
    blkArea = conf['labelblankrange']
    ## debug log:
    debugLogger.dump('collecting feature for {}\n'.format(recname))
    # load sig
    QTloader = QTdb.QTloader()
    sig = QTloader.load(recname)
    if valid_signal_value(sig['sig']) == False:
        return [[],[]]
    # blank list
    blklist = None
    if recname in blkArea:
        print recname,'in blank Area list.'
        blklist = blkArea[recname]
    tX,ty = ECGrf.collectfeaturesforsig(sig,SaveTrainingSampleFolder,blankrangelist = blklist,recID = recname)
    return (tX,ty)
    

if __name__ == '__main__':
    pass
