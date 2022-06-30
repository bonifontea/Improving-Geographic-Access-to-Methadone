
# Solves the optimization model for optimal methadone clinic locations
# Accompanies the manuscript 'Improving Geographic Access to Methadone Clinics' by Bonifonte and Garcia (2022)

# Reads in census tract data (the output file from running the provided R script) and distances files.  
# Records three files : 1) locations of existing clinics and model-estimated demand at each
#                       2) Locations of newly opened clinics and model-estimated demand at each
#                       3) Results 

########################
# Parameters to change #
########################

my_dir = '' #Working directory where data is stored and results are output
#Download the distances folder and unzip it in this directory  
my_state = '' #Which state results should be run for; use the full state name with a capital first letter ex: "Alabama"
my_k = 1 #How many new clinics to open
lam = 1 # 1 for maximizing unserved demand, 0 for minimizing existing client distances, and between 0 and 1 for hybrid

########################
# Loads required libraries
import pandas as pd
import time
import csv
import os
import pickle5 as pickle
import gurobipy as gp
from gurobipy import GRB
import numpy
import sys
#######################

#Reads data about tracts, population, methadone demand, and existing clinics
tract_data = pd.read_csv(my_dir+'Full_tract_data_output.csv', index_col='GEOID', encoding='latin-1')
Existing_clinics = pd.read_csv(my_dir+'Methadone_Clinics_2020.csv', index_col='ClinicID', encoding='latin-1')


# set the working directory
os.chdir(my_dir)

#Function to read any object
def load_obj(dir, name ):
    with open(dir + name + '.pkl', 'rb') as f:
        return pickle.load(f)
    
# Function to record results
def record_results(model):
    global Results_df
    Results_df = Results_df.append(pd.DataFrame({'State':my_state,
                                            'k':k,
                                            'lambda':lam,
                                            'Objective Value':[model.objVal],
                                            'New clients':[unserved_clients.x],
                                            'Existing sum distance':[existing_sum_dist.x],
                                            'New sum distance':[new_sum_dist.x]}))

# Function to record newly opened clinics
def record_opened_clinics(model,lam):
    global Opened_clinics_df
    tol = 0.01 # Numerical tolerance in the MIP for declaring a clinic open
    solution_y = model.getAttr('x', y)
    solution_xn = model.getAttr('x', xn)
    solution_v = model.getAttr('x', v)
    for clinic in New_potential_clinics:
        if solution_y[clinic] > tol: 
            Opened_clinics_df = Opened_clinics_df.append(pd.DataFrame({'State':my_state,
                                                                        'k':k,
                                                                        'lambda':lam,
                                                                        'Clients':[solution_xn.sum('*',clinic).getValue() + solution_v.sum('*',clinic).getValue()],
                                                                        'Longitude':[state_data.at[clinic,'Tract_Lat']],
                                                                        'Latitude':[state_data.at[clinic,'Tract_Long']]}))

# Function to record existing clinics
def record_existing_clinics(model,lam):
    global Existing_clinics_df
    solution_xe = model.getAttr('x', xe)
    for clinic in Existing_clinics:
        Existing_clinics_df = Existing_clinics_df.append(pd.DataFrame({'State':my_state,
                                                                        'k':k,
                                                                        'lambda':lam,
                                                                        'Clients': [solution_xe.sum('*',clinic).getValue()],
                                                                        'Longitude':[Existing_clinics.at[clinic,'Latitude']],
                                                                        'Latitude':[Existing_clinics.at[clinic,'Longitude']]}))

#Solves optimization model with lambda weighted objective
def solve_model_lam(this_model,lam):
    global Searched_dict

    this_model.setObjective(lam*unserved_clients/scale_clients + (1-lam)*(-1*existing_sum_dist)/scale_distance, GRB.MAXIMIZE)
    this_model.optimize()   

    existing_sum_distance = existing_sum_dist.x
    new_sum_distance = new_sum_dist.x
    unserved_demand_met = unserved_clients.x
    reassigned_clients_ = reassigned_clients.x
    total_dist_here = total_dist.x
    
    Searched_dict[lam] = [existing_sum_distance,new_sum_distance,reassigned_clients_,unserved_demand_met,total_dist_here,k]
    
    record_opened_clinics(this_model,lam)
    record_existing_clinics(this_model,lam)
    
    return(existing_sum_distance,unserved_demand_met)

##########################################################
##########################################################
## Set up model except objective function and k constraint
state_data = tract_data[tract_data.State == my_state]
state_data = state_data[state_data.Tract_Population > 0] #Restrict to only those with positive population

existing_distance = load_obj(my_dir + 'Distances/Existing Clinics/', my_state)
served_new_distance = load_obj(my_dir +'/Distances/Served Tracts/', my_state)
unserved_new_distance = load_obj(my_dir +'/Distances/Unserved Tracts/', my_state)

A0 = k0_Solutions.at[my_state,'Average Distance']
# Scaling paramaters for lambda weighting
scale_clients = k0_Solutions.at[my_state,'Unmet Demand']
scale_distance = k0_Solutions.at[my_state,'Total Distance']

Served_Tracts = set([tract for tract in list(state_data.index) if state_data.at[tract,'Tract_methadone_served']>0])
Unserved_Tracts = set([tract for tract in list(state_data.index) if state_data.at[tract,'Tract_methadone_unserved']>0])
New_potential_clinics = set([item[1] for item in list(served_new_distance.keys())]+[item[1] for item in list(unserved_new_distance.keys())])
Existing_clinics = set([item[1] for item in list(existing_distance.keys())])

#Define set of unserved clients
Unserved_tracts_by_new_clinics = {}
for clinic in New_potential_clinics:
    Unserved_tracts_by_new_clinics[clinic] = set(item[0] for item in list(unserved_new_distance.keys()) if item[1]==clinic)

#Define demand
served_demand, unserved_demand = {},{}
for tract in Served_Tracts:
    served_demand[tract] = state_data.at[tract,'Tract_methadone_served']
for tract in Unserved_Tracts:
    unserved_demand[tract] = state_data.at[tract,'Tract_methadone_unserved']

total_unserved_demand = sum(state_data['Tract_methadone_unserved'])
total_served_demand = sum(state_data['Tract_methadone_served'])

existing_flow, existing_dist = gp.multidict(existing_distance)
served_new_flow, served_new_dist = gp.multidict(served_new_distance)
if not bool(unserved_new_distance): #Dictionary is Empty
    unserved_new_flow, unserved_new_dist = {},{}
else:
    unserved_new_flow, unserved_new_dist = gp.multidict(unserved_new_distance)

######
# Setup Model
flmodel = gp.Model("Facility Location")
flmodel.setParam('OutputFlag', 0) #Suppresses messy output
#flmodel.setParam('UpdateMode', 0) #Make better use of warm start?

##################
## Variables
# Served demand at existing clinics
xe = flmodel.addVars(existing_flow, vtype=GRB.CONTINUOUS, name="xe")

# Served demand at new clinics
xn = flmodel.addVars(served_new_flow, vtype=GRB.CONTINUOUS, name="xn")

# Unserved demand at new clinics
v = flmodel.addVars(unserved_new_flow, vtype=GRB.CONTINUOUS, name="v")

# New clinic binary variables
y = flmodel.addVars(New_potential_clinics, vtype=GRB.BINARY, name="y")

# Variable for supplemental interest
existing_sum_dist = flmodel.addVar(vtype=GRB.CONTINUOUS, name="existing_sum_dist") #Sum travel distance for existing clients
new_sum_dist = flmodel.addVar(vtype=GRB.CONTINUOUS, name="new_sum_dist") #Sum travel distance for new clients
total_dist = flmodel.addVar(vtype=GRB.CONTINUOUS, name="total_sum_dist") #Sum travel distance for all clients
unserved_clients = flmodel.addVar(vtype=GRB.CONTINUOUS, name="unserved_clients")
z = flmodel.addVar(vtype=GRB.BINARY, name="z") #Indicator for whether bonus for unserved client distance is attained
reassigned_clients = flmodel.addVar(vtype=GRB.CONTINUOUS, name="reassigned_clients")
reassigned_distance = flmodel.addVar(vtype=GRB.CONTINUOUS, name="reassigned_distance")

################
## Constraints 
# Served demand satisfied constraint
served_demand_cons = flmodel.addConstrs((xe.sum(tract,'*') + xn.sum(tract,'*') == served_demand[tract] for tract in Served_Tracts), name="served_demand")

# Unserved demand up to maximum demand
unserved_demand_cons = flmodel.addConstrs((v.sum(tract,'*') <= unserved_demand[tract] for tract in Unserved_Tracts), name="unserved_demand")

# Only use new clinics that are opened
opened_cons_old = flmodel.addConstrs((xn[tract,clinic] <= served_demand[tract]*y[clinic] for (tract,clinic) in xn), name="old_demand")
opened_cons_new = flmodel.addConstrs((v[tract,clinic] <= unserved_demand[tract]*y[clinic] for (tract,clinic) in v), name="new_demand")

#Enforce that if a new clinic is opened, all possible unmet demand in it's radius must be served
forced_demand = flmodel.addConstrs((v.sum(tract,'*') >= unserved_demand[tract]*y[clinic] for clinic in New_potential_clinics for tract in Unserved_tracts_by_new_clinics[clinic]), name="forced_demand")

# Restrict number of opened clinics (0 for initialization)
k_cons = flmodel.addConstr(y.sum('*') <= 0, name="k_cons")

# Sum dist 
existing_sum_dist_const = flmodel.addConstr(xe.prod(existing_dist) + xn.prod(served_new_dist) == existing_sum_dist)
new_sum_dist_const = flmodel.addConstr(v.prod(unserved_new_dist) == new_sum_dist)
total_dist_const = flmodel.addConstr(total_dist == existing_sum_dist + new_sum_dist)

# Unserved clients
#unserved_client_const = flmodel.addConstr(sum(v.sum(tract,'*') for tract in Unserved_Tracts) == unserved_clients)
unserved_client_const = flmodel.addConstr(v.sum() == unserved_clients)

# Reassigned clients
reassigned_client_const = flmodel.addConstr(xn.sum() == reassigned_clients)

# Reassigned distance
reassigned_distance_const = flmodel.addConstr(xn.prod(served_new_dist) == reassigned_distance)

################
## Objective function
flmodel.setObjective(0, GRB.MAXIMIZE) #Initialize
flmodel.Params.TimeLimit = 10*60 # 10 minute time limit
 
sys.stdout.flush()

############################################
## evaluate the specific value of k that we are interested   
Opened_clinics_df = pd.DataFrame(columns = ["State", "k", "lambda","Clients","Longitude", "Latitude"])
Existing_clinics_df = pd.DataFrame(columns = ["State", "k", "lambda","Clients","Longitude", "Latitude"])
#Results_df = pd.DataFrame(columns = ["State", "k", "lambda",'Objective Value','New clients', 'Existing sum distance','New sum distance', 'Run Time'])
flmodel.remove(k_cons)
k_cons = flmodel.addConstr(y.sum('*') <= my_k, name="k_cons")

# Define searched dictionary and initialize it with 0 and 1
# Each entry is a list with three values : existing sum travel distance, new sum travel distance, and unserved demand met
Searched_dict = {}
solve_model_lam(flmodel,0.01)
solve_model_lam(flmodel,0.99)

# Define list of tuples to search : each is (LB,UB)
to_search_list = [(0.01,0.99)]

# Run loop
while len(to_search_list) != 0: #Not empty  
    print(f"Searching {to_search_list[0]} of k={k}")
    sys.stdout.flush()        
    bisection(flmodel,to_search_list[0])
    
        
#Write initial results files with headers
#all files will be written to the directory specified at the top of the code (my_dir)
Results_df = pd.DataFrame(columns = ['lambda','Existing Sum travel distance','New Sum travel distance','Reassigned Clients','Unserved Clients met','Total Distance','k','state'])
Results_df.to_csv(path_or_buf=my_dir + "Hybrid_Results.csv",
                                    sep=",",
                                    mode='a',
                                    index = False)

Opened_clinics_df = pd.DataFrame(columns = ["State", "k", "lambda","Clients","Longitude", "Latitude"])
Opened_clinics_df.to_csv(path_or_buf=my_dir +"Hybrid_New_Clinics.csv",
                                    sep=",",
                                    mode='a',
                                    index = False)

Existing_clinics_df = pd.DataFrame(columns = ["State", "k", "lambda","Clients","Longitude", "Latitude"])
Existing_clinics_df.to_csv(path_or_buf=my_dir +"Hybrid_Existing_Clinics.csv",
                                    sep=",",
                                    mode='a',
                                    index = False)
        
 
searched_df = pd.DataFrame(list(Searched_dict.items()),columns = ['lambda','mix']).sort_values(by='lambda')
searched_df[['Existing Sum travel distance','New Sum travel distance','Reassigned Clients','Unserved Clients met','Total Distance','k']] = pd.DataFrame(searched_df.mix.tolist(), index= searched_df.index)
searched_df[['State']] = my_state
searched_df = searched_df.drop(['mix'],axis=1)
searched_df.to_csv(path_or_buf=my_dir + "Hybrid_Results.csv",
                        sep=",",
                        mode='a',
                        header=False,
                        index = False)

Opened_clinics_df = Opened_clinics_df.sort_values(by=['k','lambda'])
Opened_clinics_df.to_csv(path_or_buf=my_dir + "Hybrid_New_Clinics.csv",
                            sep=",",
                            mode='a',
                            header=False,
                            index = False)
Existing_clinics_df = Existing_clinics_df.sort_values(by=['k','lambda'])
Existing_clinics_df.to_csv(path_or_buf=my_dir + "Hybrid_Existing_Clinics.csv",
                            sep=",",
                            mode='a',
                            header=False,
                            index = False)

