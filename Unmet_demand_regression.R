# Reads in data about tract geographies and population
# Builds a regression model of state-level demand
# Predicts Unmet demand at a state-level
# Distributes met and unmet demand to census tracts proportional to heroin usage


########################
# Parameters to change #
########################

#Working directory where data is stored
#update this for your own file system
#my_dir = ""  #Enter your working directory here
my_dir = "C:/Users/emg0039/Documents/Research/Opioids/Methadone Facility Location/code files after re-submission/"
#######################
#Loads required libraries
library(dplyr)
library(ggplot2)
library(MASS)

#Reads tract data in
tract_data = read.csv(paste(my_dir,'Full_tract_data.csv',sep=''))

# Split tract data into those within 25 miles of nearest methadone clinic, and those outside 25 miles
tracts_within_25 = subset(tract_data, Nearest_clinic <= 25)
tracts_outside_25 = subset(tract_data, Nearest_clinic > 25)


# For those outside 25 miles:
# Count up heroin usage within 25 miles of existing clinics for each state
# Build regression model predicting state methadone usage
# Predict unserved demand in rest of each state
# Distribute to tracts proportional to heroin usage

#Creates state summary data for regression
Reg_data = tracts_within_25 %>%
  group_by(State) %>%
  summarise(Heroin_within_r = sum(Heroin_Avg_Use),
            state_served_methadone = min(State_methadone_served))

#Builds regression model predicting state served demand with heroin use predictor
Heroin_model = lm(state_served_methadone ~ Heroin_within_r,
                 data = Reg_data)

#Create unserved at state level
State_unserved_data = tracts_outside_25 %>%
  group_by(State) %>%
  summarise(Heroin_outside_r = sum(Heroin_Avg_Use),
            state_served_methadone = min(State_methadone_served))

#Predict unserved demand:
State_unserved_data = State_unserved_data %>%
              mutate(State_methadone_unserved =  Heroin_outside_r * Heroin_model$coefficients[2])

#Add heroin usage and demand prediction back to complete data
tracts_outside_25 = left_join(tracts_outside_25,Reg_data[,c(1,2)], by="State") #Add within r heroin usage
tracts_within_25 = left_join(tracts_within_25,Reg_data[,c(1,2)], by="State") #Add within r heroin usage
tracts_outside_25 = left_join(tracts_outside_25,State_unserved_data[,c(1,2,4)], by="State") #Add outside r heroin usage and state unmet demand
tracts_within_25 = left_join(tracts_within_25,State_unserved_data[,c(1,2,4)], by="State") #Add outside r heroin usage and state unmet demand

#Add Tract methadone served and unserved demand to data proportional to heroin usage
tracts_outside_25 = tracts_outside_25 %>%
                      mutate(Tract_methadone_unserved = Heroin_Avg_Use/Heroin_outside_r * State_methadone_unserved)

tracts_within_25 = tracts_within_25 %>%
                      mutate(Tract_methadone_served = Heroin_Avg_Use/Heroin_within_r * State_methadone_served)

#Add blank columns
tracts_within_25$Tract_methadone_unserved = 0
tracts_outside_25$Tract_methadone_served = 0

#Combines together
full_data = rbind(tracts_outside_25, tracts_within_25)

#Saves completed data as .csv
write.table(full_data, 
            paste(my_dir,'Full_tract_data_output.csv',sep=''),
            sep=",",
            row.names = FALSE)
