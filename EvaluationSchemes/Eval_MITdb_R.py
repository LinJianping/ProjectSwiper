#encoding:utf-8
"""
ECG Evaluation Module
Author : Gaopengfei
"""
import os
import sys
import json
import glob
import math
import pickle
import random
import time
import pdb
import bisect


import numpy as np
## machine learning methods
from sklearn.ensemble import RandomForestClassifier
import matplotlib.pyplot as plt

# project homepath
# 
curfilepath =  os.path.realpath(__file__)
curfolderpath = os.path.dirname(curfilepath)
projhomepath = os.path.dirname(curfolderpath)
print 'projhomepath:',projhomepath
# configure file
# conf is a dict containing keys
with open(os.path.join(projhomepath,'ECGconf.json'),'r') as fin:
    conf = json.load(fin)
sys.path.append(projhomepath)
#
# my project components
import RFclassifier.extractfeature.extractfeature as extfeature
from QTdata.loadQTdata import QTloader
from RFclassifier.evaluation import ECGstatistics
import RFclassifier.ECGRF as ECGRF 
from ECGPloter.ResultPloter import ECGResultPloter
from MITdb.MITdbLoader import MITdbLoader
from ECGPostProcessing.GroupResult import GroupClassificationResult as ECGGrouper
from csvwriter import CSVwriter

def TestingAndSaveResult():
    sel1213 = conf['sel1213']
    time0 = time.time()
    rf = ECGRF.ECGrf()
    rf.training(sel1213[0:1])
    time1 = time.time()
    print 'Training time:',time1-time0
    ## test
    rf.testmdl(reclist = sel1213[0:1])

def debug_show_eval_result(\
            picklefilename,\
            target_recname = None,\
            singleRecordFile = False\
        ):
    with open(picklefilename,'r') as fin:
        Results = pickle.load(fin)
    # convert to a list
    if singleRecordFile == True:
        Results = [Results,]
    for recind in xrange(0,len(Results)):
        # only plot target rec
        if target_recname is not None:
            print 'Current FileName: {}'.format(Results[recind][0])
            if Results[recind][0]!= target_recname:
                return 
        fResults = ECGRF.ECGrf.resfilter(Results)
        #
        # show filtered results & raw results
        # Evaluate prediction result statistics
        #

        ECGstats = ECGstatistics(fResults[recind:recind+1])
        ECGstats.eval(debug = False)
        ECGstats.dispstat0()
        ECGstats.plotevalresofrec(Results[recind][0],Results)

def LOOT_Eval(RFfolder):
    #RFfolder = os.path.join(\
            #curfolderpath,\
            #'TestResult',\
            #'t2')
    reslist = glob.glob(os.path.join(\
            RFfolder,'*.out'))
    FN =  {
                'pos':[],
                'label':[],
                'recname':[]
                }
    Err = {
                'err':[],
                'pos':[],
                'label':[],
                'recname':[]
                }

    for fi,fname in enumerate(reslist):
        with open(fname,'r') as fin:
            Results = pickle.load(fin)
        fResults = ECGRF.ECGrf.resfilter(Results)
        # show filtered results & raw results
        #for recname , recRes in Results:

        # Evaluate prediction result statistics
        #
        ECGstats = ECGstatistics(fResults[0:1])
        pErr,pFN = ECGstats.eval(debug = False)
        for kk in Err:
            Err[kk].extend(pErr[kk])
        for kk in FN:
            FN[kk].extend(pFN[kk])

    # write to log file
    EvalLogfilename = os.path.join(curfolderpath,'res.log')
    ECGstatistics.dispstat0(\
            pFN = FN,\
            pErr = Err,\
            LogFileName = EvalLogfilename,\
            LogText = 'Statistics of Results in [{}]'.\
                format(RFfolder)\
            )
    ECGstats.stat_record_analysis(pErr = Err,pFN = FN,LogFileName = EvalLogfilename)

def TestN_Eval(RFfolder,output_log_filename = os.path.join(curfolderpath,'res.log')):

    # test result file list
    picklereslist = glob.glob(os.path.join(RFfolder,'*.out'))
    # struct Init
    FN =  {
                'pos':[],
                'label':[],
                'recname':[]
                }
    Err = {
                'err':[],
                'pos':[],
                'label':[],
                'recname':[]
                }
    #========================================
    # select best round to compare with refs
    #========================================
    bRselector = BestRoundSelector()

    for fi,fname in enumerate(picklereslist):
        
        with open(fname,'rU') as fin:
            Results = pickle.load(fin)
        # filter result
        fResults = ECGRF.ECGrf.resfilter(Results)
        # show filtered results & raw results
        #for recname , recRes in Results:

        # Evaluate prediction result statistics
        #
        ECGstats = ECGstatistics(fResults)
        pErr,pFN = ECGstats.eval(debug = False)
        # one test Error stat
        print '[picle filename]:{}'.format(fname)
        print '[{}] files left.'.format(len(picklereslist) - fi)
        evallabellist,evalstats = ECGstatistics.dispstat0(\
                pFN = pFN,\
                pErr = pErr\
                )
        # select best Round 
        numofFN = len(pFN['pos'])
        if numofFN == 0:
            ExtraInfo = 'Best Round ResultFileName[{}]\nTestSet :{}\n#False Negtive:{}\n'.format(fname,[x[0] for x in Results],numofFN)
            bRselector.input(evallabellist,evalstats,ExtraInfo = ExtraInfo)

        for kk in Err:
            Err[kk].extend(pErr[kk])
        for kk in FN:
            FN[kk].extend(pFN[kk])

    # write to log file
    #EvalLogfilename = os.path.join(curfolderpath,'res.log')
    EvalLogfilename = output_log_filename
    # display error stat for each label & save results to logfile
    ECGstatistics.dispstat0(\
            pFN = FN,\
            pErr = Err,\
            LogFileName = EvalLogfilename,\
            LogText = 'Statistics of Results in FilePath [{}]'.format(RFfolder)\
            )
    with open(os.path.join(projhomepath,'tmp','Err.txt'),'w') as fout:
        pickle.dump(Err,fout)
    # find best round
    bRselector.dispBestRound()
    bRselector.dumpBestRound(EvalLogfilename)

    ECGstats.stat_record_analysis(pErr = Err,pFN = FN,LogFileName = EvalLogfilename)

class BestRoundSelector:
    '''Select the best Round'''
    std_max = {
            'P': 20,
            'R': 20,
            'T': 20,
            'Ponset': 14.3,
            'Poffset': 13.9,
            'Ronset': 8.8,
            'Roffset': 9.2,
            'Toffset': 18.6
            }
    mean_max = {
            'P': 4,
            'R': 6,
            'T': 5,
            'Ponset': 2.5,
            'Poffset': 3.1,
            'Ronset': 2.4,
            'Roffset': 4.7,
            'Toffset': 2.8
            }
    # select the best Round Unit (ms)
    def __init__(self):
        self.labellist = []
        self.beststats = []
        self.sumstd = None
        self.ExtraInfo = ""
        self.ExcMean = -1
        self.ExcStd = -1
        self.debugcnt = 0
        
    def input(self,labellist,stats,ExtraInfo = ''):
        # if better than current stats,then keep them
        if False == self.all_lower_than_standard(labellist,stats):
            return
        excmean,excstd = self.getnumof_Exceedingstats(labellist,stats)
        meanlist,stdlist = zip(*stats)
        # sum of std
        sumstd = sum(stdlist)
        if self.labellist == 0 or self.sumstd is None or (self.ExcMean>excmean and self.ExcStd >= excstd) or (self.ExcMean>=excmean and self.ExcStd > excstd) or ((self.ExcMean>=excmean and self.ExcStd >= excstd) and self.sumstd > sumstd):
            self.labellist = labellist
            self.beststats = stats
            self.sumstd = sumstd
            self.ExtraInfo = ExtraInfo
            self.ExcMean,self.ExcStd = excmean,excstd

        
    def all_lower_than_standard(self,labellist,stats):
        # class global threshold
        std_max = self.std_max
        mean_max = self.mean_max

        meanlist,stdlist = zip(*stats)
        label_std_list = zip(labellist,stdlist)
        label_mean_list = zip(labellist,meanlist)
        # cannot have inf/nan
        for meanval in meanlist:
            if np.isnan(meanval) or np.isinf(meanval):
                print 'this record has nan/inf,not included in best round selection.'
                return False
        # m and std Upper bound
        for label,std in label_std_list:
            if std > std_max[label]+4:
                return False
        for label,mean in label_mean_list:
            if abs(mean) > mean_max[label]+2:
                return False
        # the less number of bad m the better
        badn_m,badn_std = self.getnumof_Exceedingstats(labellist,stats)

        self.debugcnt += 1
        return True
    def getnumof_Exceedingstats(self,labellist,stats):
        # class global threshold
        std_max = self.std_max
        mean_max = self.mean_max

        meanlist,stdlist = zip(*stats)
        label_std_list = zip(labellist,stdlist)
        label_mean_list = zip(labellist,meanlist)
        # the less number of bad m the better
        badn_m,badn_std = 0,0
        for label,std in label_std_list:
            if std > std_max[label]:
                badn_std += 1
        for label,mean in label_mean_list:
            if abs(mean) > mean_max[label]:
                badn_m += 1
        return (badn_m,badn_std)
       
    def dumpBestRound(self,LogFileName):
        res = zip(self.labellist,self.beststats)
        with open(LogFileName,'a') as fout:
            fout.write('\n{}\n'.format('='*40))
            fout.write('{}\n'.format(self.ExtraInfo))
            fout.write('\n>>Best Round statistics Format:[label: (mean,std) ]<<\n')
            fout.write('\n number of error exceeds refs: [mean:{},std:{}]\n'.format(self.ExcMean,self.ExcStd))
            for elem in res:
                fout.write('{}\n'.format(elem))
            
    def dispBestRound(self):
        res = zip(self.labellist,self.beststats)
        print '='*40
        print self.ExtraInfo
        print '>>Best Round statistics [label: (mean,std) ]<<'
        print 'Error Exceedings: [mean:{},std:{}]'.format(self.ExcMean,self.ExcStd)
        print 'debugcnt:',self.debugcnt
        for elem in res:
            print elem
        

def EvalQTdbResults(resultfilelist):
    if resultfilelist==None or len(resultfilelist)==0:
        print "Empty result file list!"
        return None
    FN =  {
                'pos':[],
                'label':[],
                'recname':[]
                }
    Err = {
                'err':[],
                'pos':[],
                'label':[],
                'recname':[]
                }
    #========================================
    # select best round to compare with refs
    #========================================
    bRselector = BestRoundSelector()
    InvalidRecordList = conf['InvalidRecords']

    # for each record test result
    for fi,fname in enumerate(resultfilelist):
        
        with open(fname,'rU') as fin:
            Results = pickle.load(fin)
        # skip invalid records
        currecordname = Results[0]
        if currecordname in InvalidRecordList:
            continue
        Results = [Results,]
        # filter result
        fResults = ECGRF.ECGrf.resfilter(Results)
        # show filtered results & raw results
        #for recname , recRes in Results:

        # Evaluate prediction result statistics
        #
        ECGstats = ECGstatistics(fResults)
        pErr,pFN = ECGstats.eval(debug = False)
        # one test Error stat
        print '[picle filename]:{}'.format(fname)
        print '[{}] files left.'.format(len(resultfilelist) - fi)
        evallabellist,evalstats = ECGstatistics.dispstat0(\
                pFN = pFN,\
                pErr = pErr\
                )
        # select best Round 
        numofFN = len(pFN['pos'])
        if numofFN == 0:
            ExtraInfo = 'Best Round ResultFileName[{}]\nTestSet :{}\n#False Negtive:{}\n'.format(fname,[x[0] for x in Results],numofFN)
            bRselector.input(evallabellist,evalstats,ExtraInfo = ExtraInfo)

        for kk in Err:
            Err[kk].extend(pErr[kk])
        for kk in FN:
            FN[kk].extend(pFN[kk])

    # write to log file
    #EvalLogfilename = os.path.join(curfolderpath,'res.log')
    output_log_filename = os.path.join(curfolderpath,'res.log')
    EvalLogfilename = output_log_filename
    # display error stat for each label & save results to logfile
    ECGstatistics.dispstat0(\
            pFN = FN,\
            pErr = Err,\
            LogFileName = EvalLogfilename,\
            LogText = 'Statistics of Results in FilePath [{}]'.format(os.path.split(resultfilelist[0])[0])\
            )
    with open(os.path.join(projhomepath,'tmp','Err.txt'),'w') as fout:
        pickle.dump(Err,fout)
    # find best round
    bRselector.dispBestRound()
    bRselector.dumpBestRound(EvalLogfilename)

    ECGstats.stat_record_analysis(pErr = Err,pFN = FN,LogFileName = EvalLogfilename)

def getresultfilelist():
    RFfolder = os.path.join(\
           projhomepath,\
           'TestResult',\
           'pc',\
           'r5')
    # ==========================
    # plot prediction result
    # ==========================
    reslist = glob.glob(os.path.join(\
           RFfolder,'*'))
    ret = []
    for fpath in reslist:
        len_path = len(fpath)
        if fpath.find('.json') == len_path-5:
            print '.json: ',fpath
            continue
        ret.append(fpath)
    return ret
    
def QTEval():
    RFfolder = os.path.join(\
           projhomepath,\
           'TestResult',\
           'pc',\
           'r4')
    # ==========================
    # plot prediction result
    # ==========================
    reslist = glob.glob(os.path.join(\
           RFfolder,'*'))
    for fi,fname in enumerate(reslist):
        curfname = os.path.split(fname)[1]
        if '.json' in curfname:
            continue
        if os.path.split(fname)[1] != 'hand284.out':
            pass
            #continue
        print 'File name:',fname
        debug_show_eval_result(fname,singleRecordFile = True)#,target_recname = 'sele0612')

    # ==========================
    # show evaluation statistics
    # ==========================
    #LOOT_Eval(RFfolder)
    
def get_training_testing_record_number():
    # get the number of training & testing records
    traininglist = conf['selQTall0']
    pdb.set_trace()
    testlist = getresultfilelist()
    # filter testlist
    eval_testlist = []
    invalidlist = conf['InvalidRecords']
    for testrec in testlist:
        print 'processing record:{}'.format(testrec)
        with open(testrec,'r') as fin:
            (recname,resdata) = pickle.load(fin)
        if recname not in invalidlist:
            eval_testlist.append(recname)

    num_training = len(traininglist)
    num_testing = len(eval_testlist)
    print 'num of training rec:{}'.format(num_training)
    print 'num of testing rec:{}'.format(num_testing)
    print 'total record number : {}'.format(num_training+num_testing)
def getRRhisto():
    ## plot RR histogram
    from MedEvaluationClass import MedEvaluation
    # get test result list
    testlist = getresultfilelist()
    # filter testlist
    invalidlist = conf['InvalidRecords']
    for testrec in testlist:
        print 'processing record:{}'.format(testrec)
        with open(testrec,'r') as fin:
            (recname,resdata) = pickle.load(fin)
            if recname in invalidlist:
                continue
            # RR histo
            medeval = MedEvaluation(resdata)
            medeval.RRhistogram()
            # load signal rawdata
            qtloader = QTloader()
            ECGsigstruct = qtloader.load(recname = recname)
            ECGsig = ECGsigstruct['sig']
            medeval.RRhisto_check(ECGsig)

def plotMITdbTestResult():
    RFfolder = os.path.join(\
           projhomepath,\
           'TestResult',\
           'pc',\
           'r3')
    TargetRecordList = ['sel38','sel42',]
    # ==========================
    # plot prediction result
    # ==========================
    reslist = glob.glob(os.path.join(\
           RFfolder,'*'))
    for fi,fname in enumerate(reslist):
        # block *.out
        # filter file name
        if fname[-4:] == '.out' or '.json' in fname:
            continue
        currecname = os.path.split(fname)[-1]
        if currecname not in TargetRecordList:
            pass
        if not currecname.startswith('result'):
            continue
        print 'processing file name:',fname
        with open(fname,'r') as fin:
            (recID,reslist) = pickle.load(fin)
        # load signal
        mitdb = MITdbLoader()
        rawsig = mitdb.load(recID)
        # plot res
        # group result labels
        resgrper = ECGGrouper(reslist)
        reslist = resgrper.resultfilter(reslist)

        resploter = ECGResultPloter(rawsig,reslist)
        dispRange = (20000,21000)
        savefolderpath = ur'E:\ECGResults\MITdbTestResult\pic'
        # debug
        #pdb.set_trace()
        #resploter.plot()
        resploter.plot(plotTitle = 'ID:{},Range:{}'.format(recID,dispRange),dispRange = dispRange)

def FN_stat(csvfilepath = r'MITdb_FalseNegtive_stat.csv'):
    # analysis false negtive status
    RFfolder = os.path.join(\
           projhomepath,\
           'TestResult',\
           'pc',\
           'r3')
    # write FN statistics to csv file
    csv = CSVwriter(csvfilepath)
    TargetRecordList = ['sel38','sel42',]
    # ==========================
    # analysis FN 
    # ==========================
    match_dist_thres = 50
    nFN = 0
    nExpLabel = 0
    reslist = glob.glob(os.path.join(RFfolder,'*'))
    for fi,fname in enumerate(reslist):
        # block *.out
        # filter file name
        if fname[-4:] == '.out' or '.json' in fname:
            continue
        currecname = os.path.split(fname)[-1]
        if currecname not in TargetRecordList:
            pass
        if not currecname.startswith('result'):
            continue
        print 'processing file name:',fname
        with open(fname,'r') as fin:
            (recID,reslist) = pickle.load(fin)
        # load signal
        cFN = 0
        cExpLabel = 0
        mitdb = MITdbLoader()
        rawsig = mitdb.load(recID)
        # plot res
        # group result labels
        resgrper = ECGGrouper(reslist)
        reslist = resgrper.resultfilter(reslist)
        res_poslist,res_labellist = zip(*reslist)
        #--------------------------------------
        # for each expert label find its closest match,if distance of this match exceeds match_dist_thres,then it is a classification dismatch.
        N_res = len(res_poslist)
        cExpLabel = len(mitdb.markpos)
        for expmpos in mitdb.markpos:
            # find the closest match in reslist
            close_ind = bisect.bisect_left(res_poslist,expmpos)
            matchdist = abs(res_poslist[close_ind]-expmpos)
            if close_ind+1<N_res:
                matchdist = min(matchdist,abs(res_poslist[close_ind+1]-expmpos))
            if matchdist>match_dist_thres:
                cFN+=1
        # to csv
        csv.output([[fname,cFN,cExpLabel],])
        # total stat
        nFN += cFN
        nExpLabel += cExpLabel
        print
        print 'record[{}] FN rate:{},PD rate:{}'.format(fname,float(cFN)/cExpLabel,1-float(cFN)/cExpLabel)
    # =================================
    # total FN
    # =================================
    print 'Total FN rate:{},PD rate:{}'.format(float(nFN)/nExpLabel,1.0-float(nFN)/nExpLabel)

        
class FNanalyser:
    # todo..
    # unused
    def __init__(self):
        # number of False Negtives
        self.nFN = 0
        # number of expert labels
        self.nExpLabel = 0
        pass
    def analyserecord(self,reslist,expertlabellist):
        pass
if __name__ == '__main__':
    FN_stat()
    sys.exit()
    EvalQTdbResults(getresultfilelist())