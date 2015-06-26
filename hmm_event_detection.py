# -*- coding: utf-8 -*-
"""
Created on Tue May  5 12:31:30 2015

@author: Brian Donovan (briandonovan100@gmail.com)
"""

from hmmlearn.hmm import MultinomialHMM
from numpy import array

from tools import *
from measureOutliers_gy import readGlobalPace, getExpectedPace
import csv


#Read the time-series outlier scores from file.  Note that this file should be generated by measureOutliers.py
#Arguments:
    #filename - the name of the file where outlier scores are saved
#Returns:
    #a dictionary which maps (date, hour, weekday) to the calculated mahalanobis distance
def readOutlierScores(filename):
    r = csv.reader(open(filename, "r"))
    r.next()
    mahal_timeseries={}
    c_timeseries = {}
    
    for (date,hour,weekday,mahal5,mahal10,mahal20,mahal50,c_val,gamma,tol,pca_dim,
             num_guess,hi_pcs,global_pace,expected_pace,sd_pace) in r:
        hour = int(hour)
        mahal_timeseries[(date,hour,weekday)] = float(mahal10)
        c_timeseries[(date,hour,weekday)] = int(c_val)

    return mahal_timeseries, c_timeseries



def get_event_properties(start_id, end_id, dates_list, mahal_list, 
                         global_pace_list, expected_pace_list):
    duration = end_id - start_id
    
    pace_devs = [global_pace_list[i] - expected_pace_list[i] for i in xrange(start_id, end_id)]
    min_pace_dev = min(pace_devs) / 60
    max_pace_dev = max(pace_devs) / 60
    max_mahal = max(mahal_list[start_id:end_id])
    
    (date, hour, weekday) = dates_list[start_id]
    start_date = datetime.strptime(date, "%Y-%m-%d") + timedelta(hours = int(hour))
    
    (date, hour, weekday) = dates_list[end_id - 1]
    end_date = datetime.strptime(date, "%Y-%m-%d") + timedelta(hours = int(hour))
    return [start_date, end_date, duration, max_mahal, max_pace_dev, min_pace_dev]
    


def get_all_events(states, dates_list, mahal_list, global_pace_list, expected_pace_list):
    currently_in_event = False
    events = []
    for i in xrange(len(states)):
        
        if(not currently_in_event and states[i]==1):
            event_start_id = i
            currently_in_event = True
        
        if(currently_in_event and states[i] == 0):
            event_end_id = i
            currently_in_event = False
            
            event_properties = get_event_properties(event_start_id, event_end_id,
                                    dates_list, mahal_list, global_pace_list,
                                    expected_pace_list)
            
            events.append(event_properties)
    
    return events
            
            
            
            
def augment_outlier_scores(in_file, out_file, predictions):
    with open(in_file, 'r') as in_f:
        with open(out_file, 'w') as out_f:
            r = csv.reader(in_f)
            w = csv.writer(out_f)
            
            header = r.next() + ['state']
            w.writerow(header)
            i = 0
            for line in r:
                new_line = line + [predictions[i]]
                w.writerow(new_line)
                i += 1
                


# Set up the hidden markov model.  We are modeling the non-event states as "0"
# and event states as "1"

# Transition matrix with heavy weight on the diagonals ensures that the model
# is likely to stick in the same state rather than rapidly switching.  In other
# words, the predictions will be relatively "smooth"
DEFAULT_TRANS_MATRIX = array([[.999, .001],
                      [.001,.999]])

# Emission matrix - state 0 is likely to emit symbol 0, and vice versa
# In other words, events are likely to be outliers
DEFAULT_EMISSION_MATRIX = array([[.95, .05],
                             [.4, .6]])



def detect_events_hmm(mahal_timeseries, c_timeseries, global_pace_timeseries,
                      threshold_quant=.95, trans_matrix = DEFAULT_TRANS_MATRIX,
                      emission_matrix=DEFAULT_EMISSION_MATRIX, initial_state=None):
            
    #Sort the keys of the timeseries chronologically    
    sorted_dates = sorted(mahal_timeseries)
    
    
    (expected_pace_timeseries, sd_pace_timeseries) = getExpectedPace(global_pace_timeseries)    

    #Generate the list of values of R(t)
    mahal_list = [mahal_timeseries[d] for d in sorted_dates]
    c_list = [c_timeseries[d] for d in sorted_dates]
    global_pace_list = [global_pace_timeseries[d] for d in sorted_dates]
    expected_pace_list = [expected_pace_timeseries[d] for d in sorted_dates]

    
    #Use the quantile to determine the threshold
    sorted_mahal = sorted(mahal_list)
    threshold = getQuantile(sorted_mahal, threshold_quant)
    
    
    # The symbols array contains "1" if there is an outlier, "0" if there is not
    symbols = []
    for i in range(len(mahal_list)):
        if(mahal_list[i] > threshold or c_list[i]==1):
            symbols.append(1)
        else:
            symbols.append(0)
    
    

  
    
    # Actually set up the hmm
    model = MultinomialHMM(n_components=2, transmat=trans_matrix, startprob=initial_state)
    model.emissionprob_ = emission_matrix
    
    # Make the predictions
    lnl, predictions = model.decode(symbols)
    
    events = get_all_events(predictions, sorted_dates, mahal_list, global_pace_list,
                            expected_pace_list)
    
    # Sort events by duration, starting with the long events
    events.sort(key = lambda x: x[2], reverse=True)
    return events, predictions


def process_events(outlier_score_file, feature_dir, output_file):
    mahal_timeseries, c_timeseries = readOutlierScores(outlier_score_file)
    global_pace_timeseries = readGlobalPace(feature_dir)

    events, predictions = detect_events_hmm(mahal_timeseries, c_timeseries, global_pace_timeseries)
    
    new_scores_file = output_file.split(".")[0] + "_scores.csv"
    augment_outlier_scores(outlier_score_file, new_scores_file, predictions)
    
    with open(output_file, 'w') as f:
        w = csv.writer(f)
        w.writerow(['event', 'start_date', 'end_date', 'duration', 'max_mahal', 'max_pace_dev', 'min_pace_dev'])
        for line in events:
            w.writerow(['?'] + line)




def process_events_multiple_regions():
    #k_vals = [7,8,9,10,15,20,25,30,35,40,45,50]
    k_vals = range(7,51)
    for k in k_vals:
        score_file = 'results/coarse_features_imb20_k%d_RPCAtune_10000000pcs_5percmiss_robust_outlier_scores.csv' % k
        #feature_dir = 'featuers_imb20_k%d' % k
        feature_dir = '4year_features'
        out_file = 'results/coarse_events_k%d.csv' % k
        logMsg('Generating %s' % out_file)
        process_events(score_file, feature_dir, out_file)




if __name__ == "__main__":
    process_events_multiple_regions()
    """
    process_events('results/coarse_features_imb20_k10_RPCAtune_10000000pcs_5percmiss_robust_outlier_scores.csv',
                   '4year_features', 'results/coarse_events.csv')
                   
    process_events('results/link_features_imb20_k10_RPCAtune_10000000pcs_5percmiss_robust_outlier_scores.csv',
                   '4year_features', 'results/fine_events.csv')
    
    process_events('results/link_features_imb20_k10_PCA_10000000pcs_5percmiss_robust_outlier_scores.csv',
                   '4year_features', 'results/pca_fine_events.csv')
    """
