#!/usr/bin/env python
# -*- coding: utf-8 -*-

#STSS (Self-Targeting Spacer Searcher). This code takes a archaeal/bacterial strain and searches for incorporated phage islands and checks for a working
#CRISPR system to identify self-targeting spacers
#Returns a list of potential hits

#This script was written in 2016-2017 by Kyle Watters
#Copyright (c) 2016 Kyle Watters. All rights reserved.

#Added capability to scan Genbank files locally and converted to use Python3 in 2022 - KEW

#Dependencies include:  BLAST (local), biopython, CRT CRISPR finder tool, Clustal Omega (and thus argtable2)

from __future__ import division
from datetime import datetime
import sys, os
import subprocess
import getopt
import glob
import requests
import time
import re
import http.client
from collections import Counter
from CRISPR_definitions import Cas_proteins, CRISPR_types, Cas_synonym_list, Repeat_families_to_types, Expected_array_directions
import nucleotide_acc_to_assembly_acc
from user_email import email_address
from Bio import SeqIO
from Bio.Seq import Seq
from Bio import AlignIO
from Bio.Align import AlignInfo
from Bio import Entrez
from urllib.error import HTTPError 
Entrez.email = email_address

bin_path = os.path.dirname(os.path.realpath(__file__)) + "/bin/"
HMM_dir = os.path.dirname(os.path.realpath(__file__)) + "/HMMs/"
    
help_message = '''
STSS (Self-Targeting Spacer Search tool)
------------------------------------------

STSS.py searches a set of supplied/searched fasta genomes to look for self-targeting and collects information 
about the nature of the self-targeting spacers.

*Make sure to quote multiword search terms*

Usage:
   STSS.py [options] [--dir <directory with fasta files> | --search <"NCBI search term"> | --groups <groups_file>  | --list <Assembly_uIDs_file> ]

Options
-h, --help                      Opens help message
-v, --version                   Displays version number
--dir <directory>               Use directory of genomes (fasta-formatted) instead of searching NCBI
--search <"NCBI search term">   *Use NCBI nucleotide database to find genomes
-g, --groups <groups_file>       *Runs through a list of search terms line by line. Makes a directory for each group provided and searches it on NCBI
                                Requires a text file with a list of search terms
--list <Assem_uID_list_file>    *Search genomes based on a given list of assemblies (incompatible with search, requires list of uIDs)

-o, --prefix <string>           Prefix for filenames in output (ex. prefix of 'bagel' gives: bagel_Spacers...islands.txt)
-f, --force-redownload          Forces redownloading of genomes that were already downloaded
-n, --no-ask                    Force downloading of genomes regardless of number found (default: ask, except when using --groups)
-l, --limit <N>                 Limit Entrez search to the first N results found (default: 10000)
--CDD                           Use the Conserved Domain Database to identify Cas proteins (default is to use HMMs)
--Cas-HMMs <filename>           **Use the provided HMMs for the Cas proteins instead of the provided set
--repeat-HMMs <filename>        **Use the provided HMMs for the repeat prediction instead of the provided set
--complete-only                 Only return complete genomes from NCBI
--rerun-loci <filename>         Rerun the locus annotater to recheck the nearby locus for Type and completeness from provided sapcer search results file                   
-E, --E-value  <N>              Upper limit of E-value to filter results were applicable (default: 1e-6)
--percent-reject <N>            Percentage (of 100%) to use a cutoff from the average spacer length to reject validity of a proposed locus (default 25%)
                                Lower values are more stringent
-s, --spacers <N>               Number of spacers needed to declare a CRISPR locus (default: 3)
--min-repeat-length <N>         Minimum repeat length for the CRISPR array search (default: 18)
--max-repeat-length <N>         Maximum repeat length for the CRISPR array search (default: 45)
--min-spacer-length <N>         Minimum spacer length for the CRISPR array search (default: 18)
--max-spacer-length <N>         Maximum spacer length for the CRISPR array search (default: 45)
--pad-locus <N>                 Include a buffer around a potential locus to prevent missed repeats from
                                appearing as hits (default: 100)
-d, --Cas-gene-distance <N>     Window around an array to search for Cas proteins to determine CRISPR subtype
                                (default: 20000 - input 0 to search whole genome) 
--skip-PHASTER                  Skip PHASTER analysis                               
-p, --rerun-PHASTER <filename>  Rerun PHASTER to recheck islands from provided Spacer search results file

Notes:
    *These operations are mutually exclusive
    **When using custom HMMs, please make sure the files are in the HMMs/ directory and end in .hmm
    
'''

loci_checked = {}

def get_version():
    return "1.2.1"

class Usage(Exception):
    def __init__(self,msg):
        self.msg = msg

class Params:
    
    def __init__(self):
        pass
    
    def parse_options(self, argv):
        try:
            opts, args = getopt.getopt(argv[1:], "hvE:l:s:fp:cnd:o:g:",
                                       ["limit=",
                                       "dir=",
                                       "search=",
                                       "help",
                                       "prefix=",
                                       "rerun-loci=",
                                       "E-value=",
                                       "spacers=",
                                       "min-repeat-length=",
                                       "max-repeat-length=",
                                       "min-spacer-length=",
                                       "max-spacer-length=",
                                       "Cas-HMMs=",
                                       "repeat-HMMs=",
                                       "pad-locus=",
                                       "list=",
                                       "Cas-gene-distance=",
                                       "no-ask",
                                       "force-redownload",
                                       "percent-reject=",
                                       "complete-only",
                                       "skip-PHASTER",
                                       "rerun-PHASTER=",
                                       "CDD",
                                       "groups=",
                                       "version"])
        
        except getopt.error as msg:
            raise Usage(msg)
        default_limit = 200000
        num_limit = 0
        E_value_limit = 1e-6
        provided_dir = ''
        protein_HMM_file = HMM_dir + "HMMs_Cas_proteins.hmm"
        repeat_HMM_file = HMM_dir + "REPEATS_HMMs.hmm"
        search = ''
        rerun_loci = False
        repeats = 4
        min_repeat_length = 18
        max_repeat_length = 45
        min_spacer_length = 18
        max_spacer_length = 45
        pad_locus = 100
        complete_only = False
        skip_PHASTER = False
        rerun_PHASTER = False
        skip_alignment = True
        spacer_rerun_file = ''
        percent_reject = 25
        redownload = False
        ask = True
        CDD = False
        Cas_gene_distance = 20000
        prefix = ''
        group = False
        input_list_file = ''
        num_operations = 0


        for option, value in opts:
            if option in ("-v", "--version"):
                print("STSS.py v{0}".format(get_version()))
                exit(0)
            if option in ("-h", "--help"):
                raise Usage(help_message)  
            if option in ("-l","--limit"):
                num_limit = int(value)   
            if option in ("-E", "--E-value"):
                E_value_limit = float(value)      
            if option in ("-o","--prefix"):
                prefix = value + "_"
            if option == "--dir":
                provided_dir = str(value) + "/"
                num_operations += 1
            if option == "--search":
                search = value
                num_operations += 1
            if option == "--list":
                input_list_file = value
                num_operations += 1
            if option == "--Cas-HMMs":
                protein_HMM_file = value
            if option == "--repeat-HMMs":
                repeat_HMM_file = value
            if option == "--rerun-loci":
                rerun_loci = True
                spacer_rerun_file = value
            if option in ("-s","--spacers"):
                repeats = int(value) + 1
            if option == "--min-repeat-length":
                min_repeat_length = int(value) 
            if option == "--max-repeat-length":
                max_repeat_length = int(value) 
            if option == "--min-spacer-length":
                min_spacer_length = int(value) 
            if option == "--max-spacer-length":
                max_spacer_length = int(value) 
            if option == "--pad-locus":
                pad_locus = int(value) 
            if option == "--CDD":
                CDD = True
            if option in ('-d',"--Cas-gene-distance"):
                Cas_gene_distance = int(value) 
            if option == "--complete-only":
                complete_only = True   
            if option == "--skip-PHASTER":
                skip_PHASTER = True
            if option in ('-p','--rerun-PHASTER'):
                spacer_rerun_file = value
                rerun_PHASTER = True
                skip_PHASTER = False
            if option == "--percent-reject":
                percent_reject = int(value)    
            if option in ("-f","--force-redownload"):
                redownload = True   
            if option in ("-n","--no-ask"):
                ask = False
            if option in ("-g", "--groups"):
                num_operations += 1
                group = True
                input_list_file = value
                
            
        #package the CRT parameters together
        CRT_params = [repeats, min_repeat_length, max_repeat_length, min_spacer_length, max_spacer_length]
        
        if len(args) != 0:
            raise Usage(help_message)    
                
        if num_operations == 0:
            print("You must provide an operation to perform.\n")
            raise Usage(help_message)       
        
        if num_operations != 1 and provided_dir == '':
            print("Multiple operations are not compatible (search, list, groups). Please select one.\n")
            raise Usage(help_message)                      
        
        return args,num_limit,E_value_limit,provided_dir,search,CRT_params,pad_locus,complete_only,skip_PHASTER,percent_reject,default_limit,redownload,rerun_PHASTER,spacer_rerun_file,skip_alignment,ask,input_list_file,rerun_loci,Cas_gene_distance,HMM_dir,prefix,CDD,protein_HMM_file,repeat_HMM_file,group


def import_list(update_group_file):
    with open(update_group_file, 'r') as file1:
        groups_to_search = [x.strip() for x in file1.readlines()]
    
    return groups_to_search

def rescue_list(groups_remaining):  #Export the remaining to search so you can continue after a break (intended or unintended)
    with open("groups_remaining_export.log", 'w') as file2:
        for group in groups_remaining:
            file2.write(group + "\n")

def spacer_check(sequences, percent_reject=50, code="ATGCatgcnN"):
    
    for sequence in sequences:  #First check that all only the correct characters are used
        for base in sequence: 
            if base not in code:   
                return False 
    
    #Then check that the locus is probably real by checking if all the spacer lengths fall with a rejection percentage
    spacer_lengths = [len(spacer) for spacer in sequences]
    average_spacer_length = int(sum(spacer_lengths) / len(spacer_lengths))
    lower_limit = int(average_spacer_length * (1 - percent_reject / 100))
    upper_limit = int(average_spacer_length * (1 + percent_reject / 100))
    for spacer_length in spacer_lengths:
        if spacer_length < lower_limit or spacer_length > upper_limit:
            return False         
    return True

def print_search_criteria(search,num_limit,default_limit,provided_dir,E_value_limit,pad_locus,CRT_params,percent_reject,skip_PHASTER):

    #Output the search parameters
    with open("Search_parameters.txt","w") as search_params:
        if search != '':
            search_params.write("Search parameter:\t'{0}' (excluding phages and plasmids)\n".format(search))
            if num_limit != default_limit:
                search_params.write("Search limited to:\t{0} genomes\n".format(num_limit))
        if provided_dir != '':
            search_params.write("Genomes provided from:\t{0}\n".format(provided_dir))
            if num_limit != default_limit:
                search_params.write("Number of genomes provided limited to:\t{0} genomes\n".format(num_limit))
        search_params.write("E-value limit:\t{:.1e}\n\n".format(E_value_limit))
        if pad_locus > 0:
            search_params.write("Searching at least {0} nts away from ends of CRISPR loci.\n".format(pad_locus))
        search_params.write("Minimum spacers to declare locus:\t{0}\n".format(CRT_params[0]-1))
        search_params.write("Min/Max repeat lengths to search:\t{0}/{1}\n".format(CRT_params[1],CRT_params[2]))
        search_params.write("Min/Max spacer lengths to search:\t{0}/{1}\n".format(CRT_params[3],CRT_params[4]))
        search_params.write("Minimum adherence to average spacer length:\t{0}\n".format(str(100-percent_reject)+"%"))
        if skip_PHASTER:
            search_params.write("PHASTER analysis skipped.\n")
        
def load_provided(provided_dir,num_limit,complete_only):

    provided_WGS_counter = 0 
    provided_complete_counter = 0
    fastanames = {}   
    #If genomes were provided, load into fastanames
    files = glob.glob(provided_dir + "*.*")   #gets all files in the genome directory )
    for it in files:
        if provided_complete_counter + provided_WGS_counter == num_limit:
            break
        #See if one or a set of contigs
        name = ''
        try:
            record = SeqIO.read(it,"fasta")  #will fail if WGS or not fasta
            try:
                name = record.id.split(" ")[0].strip()   #try to get NCBI formatted Accession # out of header
            except:
                name = record.id.strip()
            fastanames[name] = [it, "provided","complete"]    
            provided_complete_counter += 1
        except ValueError:
            if not complete_only:
                try:
                    for record in SeqIO.parse(it, "fasta"):
                        try:
                            if "|" in record.id:
                                name = record.id.split("|")[0].split(" ")[0]   #try to get NCBI formatted Accession # out of header
                            else:
                                name = record.id.split("")[0]
                        except:
                            name = record.id
                        break
                    if name != '':
                        fastanames[name] = [it, "provided", "WGS"]
                        provided_WGS_counter += 1
                except:                   
                    print("File {0} doesn't seem to be formatted properly. Skipping.".format(it))
        except:
            raise
    text2 =  " to analyze for self-targeting."
    text1 = "Counted {0} complete sequences".format(provided_complete_counter)
    if not complete_only:
        text1 = text1 + " and {0} WGS contig sets provided".format(provided_WGS_counter)
    print(text1 + text2) 

    return fastanames,provided_complete_counter,provided_WGS_counter

def NCBI_search(search,database,num_limit=100000,tag="[organism]",exclude_term=" NOT phage NOT virus"):
    attempt_num = 1
    while True:
        try:
            search_term = search + tag + exclude_term   #otherwise, you get isolated viruses
            handle = Entrez.esearch(db=database,term=search_term, retmax=num_limit)
            record = Entrez.read(handle)
            handle.close()
            break
        except http.client.IncompleteRead:  #If get an incomplete read, retry the request up to 3 times
            if attempt_num == 3:
                print("http.client.IncompleteRead error at Entrez genome search step. Reached limit of {0} failed attempts.".format(attempt_num))
                return
            else:
                print("http.client.IncompleteRead error at Entrez genome search step. #{0}. Retrying...".format(attempt_num))
            attempt_num += 1
        except:
            attempt_num += 1
            raise
        time.sleep(2)
    genomes = record["IdList"]
    return genomes

def prep_assemblies_list(input_list_file, num_limit, complete_only,redownload,current_dir,prefix):
    #get the assemblies from the input file
    with open(input_list_file,'r') as file1:
        lines = file1.readlines()
    assemblies = [x.strip() for x in lines]
    
    fastanames = {}
    
    found_complete, found_WGS, total, complete_IDs, WGS_IDs, wgs_master_GIs, num_genomes = link_assembly_to_nucleotide(assemblies, num_limit, complete_only, num_genomes=0, complete_IDs=[], WGS_IDs=[], wgs_master_GIs=[], simple_return=False)
    fastanames, Acc_convert_to_GI = download_genomes(total, num_limit, num_genomes, found_complete, '', redownload,'', current_dir, found_WGS, complete_IDs, WGS_IDs,wgs_master_GIs, fastanames, False, prefix)

    return fastanames, Acc_convert_to_GI

def link_genome_to_assembly(genomes,num_limit,assemblies=[]):
    attempt_num = 1
    while True:
        try:
            handle2 = Entrez.elink(dbfrom='genome', db='assembly', id=genomes, retmax=num_limit)
            record2 = Entrez.read(handle2)
            handle2.close()
            break
        except http.client.IncompleteRead:  #If get an incomplete read, retry the request up to 3 times
            if attempt_num == 3:
                print("http.client.IncompleteRead error at Entrez step linking genomes to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                return
            else:
                print("http.client.IncompleteRead error at Entrez step linking genomes to assembly database. Attempt #{0}. Retrying...".format(attempt_num))
            attempt_num += 1
        except IndexError as e: 
            print("IndexError: ", e)
            if attempt_num == 3:
                print("Encountered problems linking genomes to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                return         
        except RuntimeError:
                #NCBI probably closed the connection early, happens with poor internet connections
                if attempt_num == 3:
                    print("Runtime error at Entrez step linking genomes to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                    return
                else:
                    print("Runtime error at Entrez step linking genomes to assembly database. Attempt #{0}. Retrying...".format(attempt_num))
                attempt_num += 1
        except:
            attempt_num += 1
        time.sleep(2)
    genome_num = 0
    for linked in record2:
        try:
            for link in linked["LinkSetDb"][0]["Link"]:
                assemblies.append(link['Id'])   
        except IndexError:
            print("No assembly links from genome ID {0}. Skipping...".format(genomes[genome_num]))
        genome_num += 1 
    
    return assemblies          

def link_assembly_to_nucleotide(assemblies,num_limit=200000,complete_only=False,num_genomes=0,complete_IDs=[],WGS_IDs=[],wgs_master_GIs=[],simple_return=True):
    
    #Because the number of links can exponentially grow from the genome links, split off and do in chunks
    assembly_chunk_size = 10; activity_ticker = 0
    for chunk in range(0,len(assemblies),assembly_chunk_size):
        assemblies_chunk = assemblies[chunk:chunk+assembly_chunk_size]  
        activity_ticker += 1
        if activity_ticker % 10 == 0:
            print("Still working, linking group {0} of {1} to nucleotide...".format(activity_ticker,len(range(0,len(assemblies),assembly_chunk_size))))
        
        attempt_num = 1
        while attempt_num < 4:
            try:
                handle3 = Entrez.elink(dbfrom='assembly', db='nuccore', id=assemblies_chunk, retmax=num_limit)
                record3 = Entrez.read(handle3)
                handle3.close()
                time.sleep(0.35)  #Delay to prevent server abuse
                break
            except http.client.IncompleteRead:  #If get an incomplete read, retry the request up to 3 times
                if attempt_num == 3:
                    print("http.client.IncompleteRead error at Entrez step linking assembly numbers to nucleotide database. Reached limit of {0} failed attempts.".format(attempt_num))
                    return
                else:
                    print("http.client.IncompleteRead error at Entrez step linking assembly numbers to nucleotide database. Attempt #{0}. Retrying...".format(attempt_num))
                attempt_num += 1  
            except HTTPError as err:
                print("Received error from server %s" % err)
                print("Attempt %i of 3" % attempt_num)
                attempt_num += 1
                time.sleep(15)
            except:
                #NCBI probably closed the connection early, happens with poor internet connections
                if attempt_num == 3:
                    print("Runtime error at Entrez step linking assembly numbers to nucleotide database. Reached limit of {0} failed attempts.".format(attempt_num))
                    return
                else:
                    print("Runtime error at Entrez step linking assembly numbers to nucleotide database. Attempt #{0}. Retrying...".format(attempt_num))
                attempt_num += 1
            time.sleep(2)
        for assembly in record3:
            num_genomes += 1
            is_WGS = False
            ref_seq = False
            genbank_IDs = []
            refseq_IDs = []
            wgs_master = ''
            for link in assembly["LinkSetDb"]:
                if link['LinkName'] == 'assembly_nuccore_refseq':
                    ref_seq = True    #gives preference to refseq data being downloaded
                    refseq_IDs = [name['Id'] for name in link['Link'] ]   
                elif link['LinkName'] == 'assembly_nuccore_insdc':
                    genbank_IDs = [name['Id'] for name in link['Link'] ]
                elif link['LinkName'] =='assembly_nuccore' and genbank_IDs == []:  #if the insdc key was already found, skip over
                    genbank_IDs = [name['Id'] for name in link['Link'] ]
                elif link['LinkName'] =='assembly_nuccore_representatives' and genbank_IDs == []:  #if the insdc key was already found, skip over
                    genbank_IDs = [name['Id'] for name in link['Link'] ]
                elif link['LinkName'] == 'assembly_nuccore_wgsmaster':
                    is_WGS = True
                    wgs_master = link['Link'][0]['Id']
            if len(complete_IDs) + len(wgs_master_GIs) < num_limit:    
                if len(refseq_IDs) == 0 and len(genbank_IDs) == 0:
                    break
                if not is_WGS and ref_seq:
                    if len(refseq_IDs) == 1:
                        complete_IDs += refseq_IDs   #Note that in the accession numbers list, each position represents a genome
                    else:
                        is_WGS = True                #If there are multiple parts associated with an assembly assume its WGS even if no master is given
                        wgs_master = str(min(int(s) for s in refseq_IDs))  #If a WGS master isn't chosen, take the lowest GI number as a master for naming purposes (to prevent renaming upon re-searching since order is not preserved by NCBI)
                elif not is_WGS and not ref_seq:
                    if len(genbank_IDs) == 1:
                        complete_IDs += genbank_IDs  
                    else:
                        is_WGS = True                  #If there are multiple parts associated with an assembly assume its WGS even if no master is given
                        wgs_master = str(min(int(s) for s in genbank_IDs))
                if is_WGS and not complete_only:   #Exclude WGS data if complete-only selected
                    if len(refseq_IDs) == 1:
                        complete_IDs += refseq_IDs   ##Treat single-piece entries as complete
                    elif len(genbank_IDs) == 1:
                        complete_IDs += genbank_IDs      
                    elif ref_seq:
                        WGS_IDs.append(refseq_IDs)   #see above for brackets.
                        wgs_master_GIs.append(wgs_master) 
                    else:
                        WGS_IDs.append(genbank_IDs)
                        wgs_master_GIs.append(wgs_master) 
        
    genbank_IDs = [];  refseq_IDs = []   #Clear some memory space
                                                                                                                                                                        
    found_complete = len(complete_IDs)
    found_WGS =  len(WGS_IDs) 
    total = found_complete + found_WGS                    

    if simple_return == True:
        return complete_IDs + WGS_IDs
    else:
        return found_complete,found_WGS,total,complete_IDs,WGS_IDs,wgs_master_GIs,num_genomes

def link_nucleotide_to_bioproject(nucleotide_list,bioprojects=[],num_limit=100000):
    attempt_num = 1
    while True:
        try:
            handle4 = Entrez.elink(dbfrom='nucleotide', db='bioproject', id=nucleotide_list, retmax=num_limit)
            record4 = Entrez.read(handle4)
            handle4.close()
            break
        except http.client.IncompleteRead:  #If get an incomplete read, retry the request up to 3 times
            if attempt_num == 3:
                print("http.client.IncompleteRead error at Entrez step linking nucleotides to bioproject database. Reached limit of {0} failed attempts.".format(attempt_num))
                return
            else:
                print("http.client.IncompleteRead error at Entrez step linking nucleotides to bioproject database. Attempt #{0}. Retrying...".format(attempt_num))
            attempt_num += 1
        except IndexError as e: 
            print("IndexError: ", e)
            if attempt_num == 3:
                print("Encountered problems linking nucleotides to bioproject database. Reached limit of {0} failed attempts.".format(attempt_num))
                return         
        except RuntimeError:
                #NCBI probably closed the connection early, happens with poor internet connections
                if attempt_num == 3:
                    print("Runtime error at Entrez step linking nucleotides to bioproject database. Reached limit of {0} failed attempts.".format(attempt_num))
                    return
                else:
                    print("Runtime error at Entrez step linking nucleotides to bioproject database. Attempt #{0}. Retrying...".format(attempt_num))
                attempt_num += 1
        except:
            attempt_num += 1
        time.sleep(2)
    nucleotide_num = 0
    for linked in record4:
        try:
            for link in linked["LinkSetDb"][0]["Link"]:
                bioprojects.append(link['Id'])   
        except IndexError:
            print("No bioproject links from nucleotide ID {0}. Skipping...".format(nucleotide_list[nucleotide_num]))
        nucleotide_num += 1 
    
    return bioprojects   
    
def link_nucleotide_to_assembly(nucleotide_list,assemblies=[],num_limit=100000):
    attempt_num = 1
    while True:
        try:
            handle4 = Entrez.elink(dbfrom='nucleotide', db='assembly', id=nucleotide_list, retmax=num_limit)
            record4 = Entrez.read(handle4)
            handle4.close()
            break
        except http.client.IncompleteRead:  #If get an incomplete read, retry the request up to 3 times
            if attempt_num == 3:
                print("http.client.IncompleteRead error at Entrez step linking nucleotides to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                return
            else:
                print("http.client.IncompleteRead error at Entrez step linking nucleotides to assembly database. Attempt #{0}. Retrying...".format(attempt_num))
            attempt_num += 1
        except IndexError as e: 
            print("IndexError: ", e)
            if attempt_num == 3:
                print("Encountered problems linking nucleotides to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                return         
        except RuntimeError:
                #NCBI probably closed the connection early, happens with poor internet connections
                if attempt_num == 3:
                    print("Runtime error at Entrez step linking nucleotides to assembly database. Reached limit of {0} failed attempts.".format(attempt_num))
                    return
                else:
                    print("Runtime error at Entrez step linking nucleotides to assembly database. Attempt #{0}. Retrying...".format(attempt_num))
                attempt_num += 1
        except:
            attempt_num += 1
        time.sleep(2)
    nucleotide_num = 0
    for linked in record4:
        try:
            for link in linked["LinkSetDb"][0]["Link"]:
                assemblies.append(link['Id'])   
        except IndexError:
            print("No assembly links from nucleotide ID {0}. Skipping...".format(nucleotide_list[nucleotide_num]))
        nucleotide_num += 1 
    
    return assemblies   
    
def search_NCBI_genomes(search,num_limit,complete_only):

    #Retrieve list of complete genome IDs from the search term
    database = "genome"
    genomes = NCBI_search(search,database,num_limit)
    
    #Link genomes found to assemblies 
    assemblies = link_genome_to_assembly(genomes,num_limit,[])
    #Link assemblies found to nucleotide records  
    found_complete,found_WGS,total,complete_IDs,WGS_IDs,wgs_master_GIs,num_genomes = link_assembly_to_nucleotide(assemblies,num_limit,complete_only,num_genomes=0,complete_IDs=[],WGS_IDs=[],wgs_master_GIs=[],simple_return=False)

    return found_complete,found_WGS,total,complete_IDs,WGS_IDs,wgs_master_GIs,num_genomes

def gather_assemblies_from_bioproject_IDs(bioprojectIDs,IDs=True,num_limit=100000,complete_only=False):

    if IDs:
        #Convert BioProject IDs to assembly numbers
        try:
            fetch_handle = Entrez.elink(dbfrom='bioproject',id=bioprojectIDs,db="assembly",retmax=num_limit)
            reader = Entrez.read(fetch_handle)
            fetch_handle.close()
        except:  #If there's an error, print the subset to find the problem entry
            print(bioprojectIDs)
            sys.exit()
        assemblies = []; ID_num = 0
        for linked in reader:
            try:
                for link in linked["LinkSetDb"][0]["Link"]:
                    assemblies.append(link['Id'])   
            except IndexError:
                print("No assembly links from nucleotide ID {0}. Skipping...".format(bioprojectIDs[ID_num]))
            ID_num += 1 
    else:
        pass ##CURRENTLY UNABLE TO LINK ASSEMBLY ACCESSION #s DIRECTLY TO NUCCORE
    
    return assemblies    

def get_Accs(IDs):
    
    Accs = []
    attempt = 1
    while attempt < 4:
        try:    
            time.sleep(1)
            handle = Entrez.efetch(db='nuccore', rettype="acc", id=IDs)   #Get Acc#s of those found from search
            for Id in handle:
                if Id.strip() != "":
                    Accs.append(Id.strip())          
            handle.close()
            break
        except BaseException as e:
            print(e)
            if attempt < 4:
                attempt += 1
                time.sleep(5)
            else:
                raise
        
    return Accs
         
def download_genomes(total,num_limit,num_genomes,found_complete,search,redownload,provided_dir,current_dir,found_WGS=0,complete_IDs=[],WGS_IDs=[],wgs_master_GIs=[],fastanames={},ask=False,prefix=''):

    if total > num_limit:
        extra_text = " Preparing to download only {0}.".format(num_limit)
    else:
        extra_text = ''
    
    if total < num_limit:
        if search != '':
            print("Found {0} genome(s) searching for '{1}'.".format(num_genomes,search))
        else:
            print("Found {0} genome(s).".format(num_genomes,search))
    else:
        extra_text = " Preparing to download only the first {0}.".format(num_limit)
        print("Found {0} genome(s) searching for '{1}'.".format(num_genomes,search) + extra_text)
    
    if not os.path.exists("{0}downloaded_genomes".format(prefix)):
            os.mkdir("{0}downloaded_genomes".format(prefix))
    num_downloaded = 0
    
    #Filter out genomes that have already been downloaded, unless forced re-download
    if not redownload:
        files = glob.glob(current_dir+"{0}downloaded_genomes/*.*".format(prefix))   #gets all files in the genome directory
        if provided_dir != '':
            files += glob.glob(provided_dir + "/*.*")   #gets all files in the provided directory to prevent doubles
        files_in_dir = {}
        for filename in files:
            #Check if the file provided is a WGS or complete genome
            frag_num = 0
            genome_type = "complete"
            with open(filename, 'r') as openfile:
                for line in openfile:
                    if line[0] == ">":
                        frag_num += 1
                        Acc_num = line.split(">")[1].split()[0].strip()
                        if frag_num > 1:
                            genome_type = "WGS"   #NOTE will assume that a file with 1 contig is a complete genome (for the purposes of the code, they run the same however)
                            Acc_num = Acc_num.split("|")[0]   #This will generate a master record number, or what it was labeled as
                            break
            files_in_dir[Acc_num] = [filename, "provided", genome_type]
        
        #Convert all of the searched GI numbers to Accession via a dictionary
        batch_size = 5 ; Accs = []
        all_IDs = complete_IDs+wgs_master_GIs
        for start in range(0, len(all_IDs), batch_size):
            end = min(len(all_IDs), start+batch_size)
            IDs = all_IDs[start:end]
            Accs += get_Accs(IDs)
        Acc_convert_to_GI = dict(zip(Accs,complete_IDs+wgs_master_GIs))
        unaccounted_files = {}
        for Acc, data in files_in_dir.items():
            try:
                GI = Acc_convert_to_GI[Acc]
                if GI in complete_IDs or GI in wgs_master_GIs:
                    fastanames[Acc] = files_in_dir[Acc]
            except KeyError:
                #If the Accession number isn't in the conversion list, there is a likely a missing WGS master record (or was and is now being supplied)
                #Specifically, the WGS master from the file isn't in the search list
                unaccounted_files[Acc] = data   #Store for a downstream search
        
        #Remove the found file from the list of names that were provided in the search
        num_complete_found = 0
        num_WGS_found = 0
        for Acc, data in fastanames.items():
            GI = Acc_convert_to_GI[Acc]
            try:
                index = complete_IDs.index(GI)
                complete_IDs.pop(index)
                num_complete_found += 1
            except:
                try:
                    index = wgs_master_GIs.index(GI)
                    wgs_master_GIs.pop(index)
                    WGS_IDs.pop(index)
                    num_WGS_found += 1
                except:
                    pass
        
        if len(unaccounted_files.keys()) > 0 and len(wgs_master_GIs) > 0:  #check to see if there are remaining files and WGS files that could be associated
            for Acc, data in unaccounted_files.items():
                if data[2] == "WGS":
                    with open(data[0], 'r') as fileobj:
                        for line in fileobj:
                            if line[0] == '>':
                                Acc_num_contig = line.split()[0].split("|")[1]
                                for Acc2 in Accs:  #Need to be explicit to search substrings in order to try to get RefSeq/INDSC renames 
                                    if Acc_num_contig in Acc2:               #if location position of misplaced WGS tag, include in search and remove from download list
                                        fastanames[Acc] = files_in_dir[Acc]   
                                        try:
                                            index = wgs_master_GIs.index(Acc_convert_to_GI[Acc2])
                                            wgs_master_GIs.pop(index)
                                            WGS_IDs.pop(index)
                                            num_WGS_found += 1 
                                            break
                                        except ValueError:
                                            pass
                                        except KeyError:
                                            pass
                                        
        if num_complete_found + num_WGS_found > 0:
            print("{0} of {1} unfragmented genomes and {2} of {3} fragmented/multi-part genomes have already been downloaded.".format(num_complete_found, found_complete, num_WGS_found, found_WGS))                                              
    else:
        Acc_convert_to_GI = {}
    
    found_complete = len(complete_IDs)   #recalculate total
    found_WGS =  len(WGS_IDs) 
    total = found_complete + found_WGS                    
    
    if total > 100 and num_limit > 100 and ask:
        while True:
            check = raw_input("The number of files to download likely exceeds 200 Mb, would you like to continue? (y/n): ")
            if check.lower() == 'y':
                print("Fetching...")
                break
            elif check.lower() == 'n':
                print("Aborting...")
                return
                break
            else:
                print("Please select yes(y) or no(n).")     
    
    #Download the complete genomes first
    batch_size = 5
    num_complete = len(complete_IDs)
    for start in range(0, num_complete, batch_size):
        end = min(num_complete, start+batch_size)
        print("Downloading unfragmented genome records %i to %i of %i" % (start+1, end, num_complete))
        attempt = 1
        IDs = complete_IDs[start:end]
        while attempt <= 3:
            try:
                fetch_handle = Entrez.efetch(db="nucleotide", rettype="fasta", retmode="text", retmax=batch_size, id=IDs)
                data = fetch_handle.read().split("\n\n")
                fetch_handle.close()
                break
            except http.client.IncompleteRead:
                if attempt == 3:
                    print("http.client.IncompleteRead error when downloading a genome. Reached limit of {0} failed attempts.".format(attempt))
                    return
                else:
                    print("http.client.IncompleteRead error when downloading a genome. Attempt #{0}. Retrying...".format(attempt))
            except HTTPError as err:
                if 500 <= err.code <= 599:
                    print("Received error from server %s" % err)
                    print("Attempt %i of 3" % attempt)
                    attempt += 1
                    time.sleep(15)
                if err.code == 429:
                    time.sleep(5)
                    print("Received error from server %s" % err)
                else:
                    raise
            attempt += 1
        for index in range(0,len(IDs)):
            Acc_num = data[index].split(" ")[0][1:]
            filename = current_dir+"{0}downloaded_genomes/".format(prefix) + Acc_num.split(".")[0] + ".fasta"
            fastanames[Acc_num] = [filename, "lookup","complete"]
            with open(filename, "w") as output:
                output.write(data[index]) 
                num_downloaded += 1                               

    #Convert the WGS names from GIs to Accession
    fetch_handle = Entrez.efetch(db="nuccore", id=wgs_master_GIs, rettype="acc", retmode="text", retmax=num_limit)
    wgs_masters_Acc = [id.strip() for id in fetch_handle]
    fetch_handle.close()
    
    #Download each WGS genome as a batch
    WGS_num = 0
    num_WGS = len(WGS_IDs)
    for WGS_sublist in WGS_IDs:
        contigs = len(WGS_sublist)  #Number of contigs in a WGS project
        if WGS_num % 10 == 0:
            print("Downloading fragmented genome records %i to %i of %i" % (WGS_num+1, min(WGS_num+10,num_WGS), num_WGS))
        attempt = 1
        while attempt <= 3:
            try:
                fetch_handle = Entrez.efetch(db="nucleotide", rettype="fasta", retmode="text", retmax=contigs, id=WGS_sublist)
                data = fetch_handle.read()
                fetch_handle.close()
                break
            except HTTPError as err:
                if 500 <= err.code <= 599:
                    print("Received error from server %s" % err)
                    print("Attempt %i of 3" % attempt)
                    attempt += 1
                    time.sleep(15)
                else:
                    raise
            except http.client.IncompleteRead:
                if attempt == 3:
                    print("http.client.IncompleteRead error at fasta data fetch. Reached limit of {0} failed attempts.".format(attempt))
                    break
                else:
                    print("http.client.IncompleteRead error at fasta data fetch. Attempt #{0}. Retrying...".format(attempt))
            time.sleep(2)
        
        #retrieve the master accession number, stored from before
        if data != []:
            Acc_num = wgs_masters_Acc[WGS_num]
            pieces = data.split("\n\n")
            filename = current_dir+"{0}downloaded_genomes/".format(prefix) + Acc_num.split('.')[0] + ".fasta"
            fastanames[Acc_num] = [filename, "lookup", "WGS"]                 
            
            with open(filename, "w") as output:                         #(other catches later will recognize the Accession #)
                for piece in pieces:
                    if piece != '':
                        true_accession = piece.split(" ")[0][1:].strip()
                        header = ">{0}|{1}\n".format(Acc_num,true_accession)
                        output.write(header)
                        output.write("".join(piece.split("\n")[1:]) + "\n")
                num_downloaded += 1              
        WGS_num += 1
    complete_IDs = []  #clear memory space
    WGS_IDs = []
    
    if num_downloaded > 0:                                                                                                                  
        print("Downloaded {0} new sequences to analyze for self-targeting sequences.".format(num_downloaded))
    else:
        print("No need to download more sequences.")

    return fastanames,Acc_convert_to_GI

def spacer_scanner(fastanames,bin_path,CRT_params,current_dir,prefix):

    #Search each genome for CRISPR repeats
    print("Searching for CRISPR spacer-repeats...")
    CRISPR_results = []    #list of files with CRISPR loci search results
    genomes_searched = []
    bad_genomes = []
    affected_genomes = {}
    Ns = "N"*500
    try: 
        os.remove("{0}genomes_with_long_stretches_of_Ns.txt".format(prefix))
    except:
        pass
    for fastaname, holder in fastanames.items():
        good_genome = True
        filein = holder[0]
        if not os.path.exists("{0}CRISPR_analysis".format(prefix)):
            os.mkdir("{0}CRISPR_analysis".format(prefix))
        fasta_sequences = SeqIO.parse(open(filein),'fasta')
        #Check that the genome file has data in it
        with open(filein, 'r') as file1:
            lines = file1.readlines()
        if len(lines) <= 1:
            print('No genomic data in {0}. Skipping...'.format(fastaname))
            good_genome = False
        else:
            line_no = 0; abs_pos = 0; affected_lines = []; names = []; sequences = []
            fasta_sequences = SeqIO.parse(open(filein),'fasta')
            for fasta in fasta_sequences:
                    names.append(">" + str(fasta.name) + "\n")
                    sequences.append(str(fasta.seq) +"\n")
            for seq in sequences:
                if Ns in seq:
                    if affected_lines == []:
                        print('Long string of Ns in {0}. Modifying fasta file. Positions will be adjusted...'.format(fastaname))
                        with open("genomes_with_long_stretches_of_Ns.txt", "a") as file1:
                            file1.write(fastaname+'\n')
                    #Look for instances of long strings of Ns, need to search line by line, as well as within each line
                    seq_temp = seq
                    Ns_position = seq_temp.find(Ns)
                    adj_leng = 200  #number of Ns to remove in a chunk
                    while Ns_position != -1:
                        Ns_position_orig = Ns_position
                        pos_adjust = 0
                        while Ns_position == Ns_position_orig:
                        #Find where the Ns are, and remove 200 then note that the positions have been altered by 200, then repeat and look for again
                            seq_temp = seq_temp[:Ns_position] + seq_temp[Ns_position+adj_leng:]
                            pos_adjust += adj_leng
                            Ns_position = seq_temp.find(Ns)
                        sequences[line_no] = seq_temp
                        affected_lines.append([abs_pos+Ns_position_orig,pos_adjust])  #will store where the replacements are occuring  
                abs_pos += len(sequences[line_no].strip()) + len(names[line_no].strip())
                line_no += 1
            if affected_lines != []:
                mod_dir = "/".join(filein.split("/")[:-1])+"/edited_fastas/"
                mod_file = mod_dir + "".join(filein.split("/")[-1].split(".")[:-1])+"_Ns_removed.fasta"
                if not os.path.exists(mod_dir):
                    os.mkdir(mod_dir)
                with open(mod_file, 'w') as file1:
                    for i in range(0,len(names)):
                        file1.write(names[i]) 
                        file1.write(sequences[i])
                fastanames[fastaname] = [mod_file] + holder[1:]
                filein = mod_file
                #Store the affected_lines in this fastaname as a dictionary
                affected_genomes[fastaname] = affected_lines
            
        if good_genome:     
            result_file = "{0}CRISPR_analysis/".format(prefix) + fastaname.split(".")[0] + ".out"
            CRISPR_cmd = "java -cp {0}/CRT1.2-CLI.jar crt -minNR {1} -minRL {2} -maxRL {3} -minSL {4} -maxSL {5} {6} {7}".format(bin_path,CRT_params[0],CRT_params[1],CRT_params[2],CRT_params[3],CRT_params[4],filein,result_file)
            crispr_search = subprocess.Popen(CRISPR_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            output, error = crispr_search.communicate()
            if error != '':
                print(error.decode() + " Skipping {0}...".format(fastaname))
            else: 
                append = True
                try: 
                    with open(result_file, 'r') as result_check:
                        for line in result_check:
                            if line.find("No CRISPR elements were found.") != -1:  #check to make sure at least one locus was found to continue with
                                append = False
                    genomes_searched.append(fastaname)
                    if append:
                        CRISPR_results.append([result_file, fastaname])
                except IOError:   #can occur if no genome information in file (no results file)
                    bad_genomes.append(fastaname)
        else:
            bad_genomes.append(fastaname)            

    #Print out a list of the genomes analyzed
    with open("{0}genomes_analyzed.txt".format(prefix), "w") as filetemp:
        for genome in genomes_searched:
            filetemp.write(genome + "\n")
    #Print out a list of the genomes that failed analysis
    with open("genomes_failing_analysis.txt", "w") as filetemp:
        for line in bad_genomes:
            filetemp.write(line + "\n")
    
    print("Finished searching for CRISPR spacer-repeats.")

    return CRISPR_results, affected_genomes

def get_loci(CRISPR_results,fastanames,affected_genomes={}):

    #Data is stored at the uppermost level as each genome
    #Next level is the Acc # (0 index) and a list containing the CRISPR # and 2 member lists of the spacer sequences and their positions
    spacer_data = []
    genome_counter = 0
    num_loci = []
    for genome in CRISPR_results:
        with open(genome[0], 'r') as curr_file:
            lines = curr_file.readlines()
            if fastanames[genome[1]][1] == 'lookup' and fastanames[genome[1]][2] == 'complete':
                spacer_data.append([[lines[0].split("ORGANISM:  ")[1].split(" ")[0].strip(), 'lookup', 'complete']])  #if looked up, this should be the accession number
            elif fastanames[genome[1]][1] == 'lookup' and fastanames[genome[1]][2] == 'WGS':
                spacer_data.append([[lines[0].split("ORGANISM:  ")[1].split("|")[0].strip(), 'lookup', 'WGS']])  #if looked up, this should be the accession number
            elif fastanames[genome[1]][1] == 'provided':
                try:
                    if "|" in lines[0].split("ORGANISM:  ")[1]:
                        spacer_data.append([[lines[0].split("ORGANISM:  ")[1].split("|")[0].strip(), 'lookup', 'WGS']])  #Try to get the accession number (will be there if using NCBI formatted headers)  
                    else:
                        spacer_data.append([[lines[0].split("ORGANISM:  ")[1].split(" ")[0].strip(), 'provided', 'WGS']])  #otherwise, take the provided name in fasta
                except:
                    spacer_data.append([[lines[0].split("ORGANISM:  ")[1].strip(), 'provided', 'WGS']])  #otherwise, take the provided name in fasta
            CRISPR_positions = []
            position = 0  
            for line in lines:
                if line[:6] == "CRISPR":
                    CRISPR_positions.append(position)
                    spacer_data[genome_counter].append([line])
                position += 1
            CRISPR_counter = 1
            if CRISPR_positions != []:   #check that at least one locus was found
                for locus in CRISPR_positions:
                    spacer_counter = 1
                    while True:
                        curr_spacer = lines[locus+2+spacer_counter].split("\t")[3]
                        if curr_spacer != '\n':
                            curr_spacer_pos = int(lines[locus+2+spacer_counter].split("\t")[0]) + int(lines[locus+2+spacer_counter].split("\t")[4].split(" ")[1][:-1])
                            spacer_data[genome_counter][CRISPR_counter].append([curr_spacer])
                            spacer_data[genome_counter][CRISPR_counter][spacer_counter].append(curr_spacer_pos)
                            spacer_counter += 1
                        else:
                            break
                    CRISPR_counter += 1
        genome_counter += 1
        num_loci.append(CRISPR_positions)         

    return spacer_data,num_loci

def spacer_BLAST(spacer_data,fastanames,num_loci,percent_reject,current_dir,bin_path,E_value_limit):

    blast_results = []
    num = 0
    for genome in spacer_data:
        #write a file of the query strings
        if not os.path.exists("queries"):
            os.mkdir("queries")
        if genome[0][1] == 'lookup':
            subject = fastanames[genome[0][0]][0]  #pulls up the file for the name provided or accession # if looked up
            #search_for = genome[0].split(".")[0]
            queryfilename = "queries/" + genome[0][0].split(".")[0] +"_queries.txt"
        else: 
            subject = fastanames[genome[0][0].split(' ')[0].strip()][0]  #pulls up the file for the name provided or accession # if looked up
            queryfilename = "queries/" + genome[0][0].split(".")[0] +"_queries.txt"         
        temp_lines = []
        for CRISPR_counter in range(1,len(num_loci[num])+1):
            spacer_checker = []
            for spacer_counter in range(1,len(genome[CRISPR_counter])):
                spacer = genome[CRISPR_counter][spacer_counter][0]  #check all the spacers, making sure they have the correct characters
                spacer_checker.append(spacer)
            if spacer_check(spacer_checker,percent_reject):
                for spacer_counter in range(1,len(genome[CRISPR_counter])):
                    spacer = genome[CRISPR_counter][spacer_counter][0]
                    temp_lines.append(">CRISPR_{0}_Spacer_{1}\n{2}\n".format(CRISPR_counter,spacer_counter,spacer))  #need an actual file for BLAST input                        
        with open(queryfilename, "w") as queryfile:
            for line in temp_lines:
                queryfile.write(line)
        blast_cmd = "{0}blastn -query {1} -subject {2} -outfmt 6 -evalue {3}".format(bin_path,queryfilename,subject,E_value_limit)
        handle = subprocess.Popen(blast_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        output, error = handle.communicate()
        blast_results.append(output.split("\n"))
        num += 1
    print("Finished BLASTing all spacer sequences.")
    
    return blast_results

def get_PAMs(direction,align_pos,sequence):
    
    if direction > 0: 
        PAM_start = align_pos-1
        PAM_seq_up = sequence[PAM_start-9:PAM_start].upper() 
        
        PAM_start = align_pos+abs(direction)
        PAM_seq_down = sequence[PAM_start:PAM_start+9].upper()  
    else:
        PAM_start = align_pos
        a = sequence[PAM_start:PAM_start+9].upper()
        PAM_seq_up = str(Seq(a).reverse_complement())
        
        PAM_start = align_pos-abs(direction)-1
        a = sequence[PAM_start-9:PAM_start].upper()
        PAM_seq_down = str(Seq(a).reverse_complement()) 
    
    return PAM_seq_up,PAM_seq_down

def fetch_sequence(fastanames,Acc_num,self_target_contig,provided_dir=''):
    
    keys = fastanames.keys()
    if provided_dir != '':
        try: 
            fastaname = fastanames[Acc_num][0]
        except:
            for key in keys:
                if key.find(Acc_num) > -1:
                    fastaname = fastanames[key][0]
                    break
    else:
        fastaname = fastanames[Acc_num][0]
    contigs = []
    fastafile = open(fastaname)
    for item in SeqIO.parse(fastafile,"fasta"):
            name, sequence = str(item.id), str(item.seq)
            contigs.append([name,sequence])
    fastafile.close()                                          
    if len(contigs) > 1:
        sequence = contigs[self_target_contig][1]
    else:
        sequence = contigs[0][1]
    
    return sequence,fastaname
    
def download_genbank(contig_Acc,bad_gb_links=[]):
    
    #First, pull down the GenBank records for each accession number with a self-targeting spacer (pull down locus)
    #Can use one record for complete genomes, may need two for contigs
    if not os.path.exists("GenBank_files"):
        os.mkdir("GenBank_files")
    attempt = 1; skip = False
    genfile_name = "GenBank_files/"+contig_Acc.split(".")[0] + ".gb"
    if contig_Acc not in bad_gb_links:
        while attempt <= 3:
            try:
                #First get the genbank format and parse into SeqIO
                if not os.path.isfile(genfile_name):
                    fetch_handle = Entrez.efetch(db="nucleotide", rettype="gbwithparts", retmode="text", id=contig_Acc)
                    data = fetch_handle.read()                        
                    fetch_handle.close()
                    if data != '':
                        with open(genfile_name, 'w') as genfile:
                            genfile.write(data)
                    else:
                        if attempt == 3:
                            print('No data in Genbank file for contig {0} Skipping...'.format(contig_Acc))
                            skip = True
                break
            except http.client.IncompleteRead:
                if attempt == 3:
                    print("http.client.IncompleteRead error at Genbank data fetch. Reached limit of {0} failed attempts.".format(attempt))
                    skip = True
                    break
                else:
                    print("http.client.IncompleteRead error at Genbank data fetch. Attempt #{0}. Retrying...".format(attempt))
            except HTTPError as err:
                if err.code != 400 :
                    print("Received error from server %s" % err)
                    print("Attempt %i of 3" % attempt)
                    attempt += 1
                    time.sleep(15)
                elif err.code == 400:  #This will happen if the name of isn't an accession number
                    print("{0} isn't a valid accession number and/or a matching *.gb file is missing".format(contig_Acc))
                    bad_gb_links.append(contig_Acc)
                    skip = True
                    break
            except ValueError as err:   #occurs when no records in a downloaded 
                print("WARNING!: {0} - no data, skipping analysis of this target...".format(err.message))
                bad_gb_links.append(contig_Acc)
                skip = True
                break
            except Exception as err:
                print("Received error %s" % err)
                print("Attempt %i of 3" % attempt)
                attempt += 1
                time.sleep(15)
        else:  #if the number of attempts is exceeded
            print("Too many failed connection attempts, please check your internet connection.")
            exit()    
    else:
        skip = True
    if skip:
        record = SeqIO.SeqRecord(Seq(""),
                   id="Missing Data", name="Missing Data",
                   description="Missing Data")
        if os.path.isfile(genfile_name):
            os.remove(genfile_name)
    else:     
        #A bad Genbank file could cause an error, give 2 tries before quitting
        for i in range(0,2):
            try:
                record = SeqIO.read(genfile_name, 'genbank')
                break
            except:
                os.remove(genfile_name)
                record = download_genbank(contig_Acc,[])
    return record    
    
def find_Cas_proteins(align_pos,record,protein_HMM_file,prefix,CDD=False,Cas_gene_distance=20000):
    
    #Define the region to examine coding regions
    if Cas_gene_distance == 0:
        upstream_pos = 1
        downstream_pos = len(record.seq)
    else:
        upstream_pos = max(1,align_pos - Cas_gene_distance)
        downstream_pos = min(align_pos + Cas_gene_distance, len(record.seq))
        
    #Search through the features and find those that fall within the range defined above
    check_list = []; check_aa = []; proteins_identified = []; types_list = []; pseudogenes = []; protein_name = ''; up_down = 0
    for feature in record.features:
        if upstream_pos <= feature.location.start <= downstream_pos:
            #Search for the CRISPR proteins and keep track of whether they are before or after the array
            if feature.type == 'CDS':
                qualifiers = feature.qualifiers
                if 'pseudo' in qualifiers:
                    pseudogene = True
                else:
                    pseudogene = False
                try:
                    protein_num = qualifiers["protein_id"][0]
                except KeyError:  #No protein_id associated, such as a pseudo-gene
                    try:
                        protein_num = qualifiers["locus_tag"][0]
                    except KeyError:
                        protein_num = 'UNKNOWN'  #will skip over if no tag at all, but should not occur (placeholder for fasta files)
                try:
                    product = feature.qualifiers["product"][0]
                    #Now determine if this feature encodes a Cas protein
                    if product == 'hypothetical protein':   #Add all hypothetical proteins by default
                        if CDD:
                            check_list.append(protein_num)
                        else:
                            aa = str(feature.extract(record).seq.translate(to_stop=True))
                            if aa != "":
                                check_list.append(protein_num)
                                check_aa.append(aa)  #Add the protein sequence
                    else:
                        #See if protein identified as Cas protein
                        is_Cas, protein_name, types_list = is_known_Cas_protein(product,types_list)
                        if is_Cas:
                            if pseudogene:
                                protein_name += " (pseudo)"
                            if Cas_gene_distance == 0:
                                protein_name += " (in {0})".format(align_pos)   
                            if protein_name not in proteins_identified and protein_name != '': 
                                proteins_identified.append(protein_name)
                                if feature.location.start < upstream_pos + Cas_gene_distance:  #if upstream of the array
                                    up_down += 1
                                else:
                                    up_down -= 1
                        else:
                            if pseudogene:
                                pseudogenes.append(protein_num)  #keep track of the pseudogenes found before homology search, since order can be lost to utilize batch processing on NCBI CD server
                                aa = str(feature.extract(record).seq.translate(to_stop=True))
                                if aa != "":
                                    check_list.append(protein_num)
                                    check_aa.append(aa)  #Add the protein sequence
                            if CDD:
                                check_list.append(protein_num)
                            else:
                                aa = str(feature.extract(record).seq.translate(to_stop=True))
                                if aa != "":
                                    check_list.append(protein_num)
                                    check_aa.append(aa)  #Add the protein sequence
                except KeyError:
                    pass  #skip CDS annotations with no id or content
    
    #Now take the proteins that weren't identified and check to see if there are any Cas proteins in them
        
    if check_list != []:
        if CDD == True:
            #Use the protein accession number to check whether they are Cas proteins
            short_names = CDD_homology_search(check_list)   #Note: order of the Cas genes is not preserved, only checks if all are present
        else:
            #Otherwise the default is search the protein sequences with HMMER to see if they are Cas proteins
            short_names = HMM_Cas_protein_search(check_list,check_aa,prefix,bin_path,protein_HMM_file)
        for short_name in short_names:    
            is_Cas,protein_name,types_list = is_known_Cas_protein(short_name.split('\t')[1],types_list)
            if is_Cas:
                if short_name.split('\t')[0] in pseudogenes:
                    protein_name += " (pseudo)"
            if protein_name not in proteins_identified and protein_name != '': 
                proteins_identified.append(protein_name)        
                if feature.location.start < upstream_pos + Cas_gene_distance:  #if upstream of the array
                    up_down += 1
                else:
                    up_down -= 1      
                                                    
    return proteins_identified,types_list,up_down

def Type_check(types_list):
    
    #Now determine what type it is and if it is complete
    #Determine the type by counting the Type that is the most prevalent
    data = Counter(types_list)
    Type = ""
    off_count = 0
    for most_common in data.most_common():
        count = most_common[1]
        if count >= off_count:
            if Type == '':
                Type = most_common[0]
            elif Type.count(",") == 1:
                Type += ", or " + most_common[0]
            else:
                Type += ", " + most_common[0]
            off_count = count
        if count < off_count or most_common == data.most_common()[-1]:  #reached end of list or found less common entry 
            if Type.count(",") > 2:  #Too many possibilities to exactly identify
                Type = "?"
            elif Type.count(",") == 1:
                Type.replace(",", " or")
                Type += "?"
            elif Type.count(",") == 2:
                Type[:Type.rfind(",")] + " or" + Type[Type.rfind(",")+1:]
                Type += "?"
            break
    if Type == "":
        Type = "?"
                
    return Type                                              

def locus_completeness_check(Type,proteins_identified):
    
    if Type.find("?") == -1:
        complete_locus = CRISPR_types[Type]    #list of lists containing each protein and its alternate names
        Cas_search = ["Proteins missing: "]
        for proteins in complete_locus:
            found_it = False
            for check in proteins_identified:  #see if the list of proteins found align with what's known
                if check.split()[0] in proteins:  #use the split to remove the pseudo tag if present
                    found_it = True
            if not found_it:
                Cas_search.append(proteins[0])
        if Cas_search == ["Proteins missing: "]: #If nothing was added the locus is complete
            Cas_search = ["Complete"]
    elif Type.find("?") > -1:  #don't check if more than three (when there will only be a ?)
        if proteins_identified == []:
            Cas_search = ["N/A"]   
        #Since Type is unknown, give a generic output
        else:
            Cas_search = ["Undetermined"]
        #List out the proteins that were identified, but need to cross reference to prevent doubles
        #for Cas, types in Cas_proteins.items():
        #    if Cas in proteins_identified and Cas not in Cas_search:
        #        Cas_search.append(Cas)
                                     
    else:    #If only a question mark (i.e., too many potential (or no) CRISPR loci to tell)
        Cas_search = ["N/A"]
    
    return Cas_search      
 
def find_spacer_target(Acc_num_target,alt_alignment):
    
    #If it isn't targeting a gene, look at gene on each side
    record = download_genbank(Acc_num_target)
    #Find which gene is targeted by the spacer
    if type(record) is not str:
        self_targets = []
        lagging_feature = ''; feature_num = ''; target_protein = ''
        for feature in record.features:
            if feature.type not in ('gene','source'):
                feature_num, target_protein = grab_feature(feature)
                if feature.location.start <= alt_alignment <= feature.location.end:  #This is the case where the self-target falls within a gene
                    target_protein = label_self_target(target_protein,feature_num)
                    self_targets.append([feature_num, target_protein])
                    break
                elif lagging_feature == '' and alt_alignment < feature.location.start:  #This is the case where the self-target is before any features    
                    target_protein = label_self_target(target_protein,feature_num)
                    self_targets.append(["upstream contig edge",""])
                    self_targets.append([feature_num, target_protein])
                    break
                elif alt_alignment < feature.location.start:   #The spacer falls in between a gene and the next gene or the end of the contig
                    target_protein = label_self_target(target_protein,feature_num)
                    self_targets.append([feature_num, target_protein])
                    self_targets.append([lagging_feature_num, lagging_target_protein])
                    break
                lagging_feature = feature
                lagging_feature_num = feature_num #Used to store first feature in case spacer falls in the middle of two genes
                lagging_target_protein = target_protein
        else:  #will reach here if running off of the end of the contig
            if len(record.features) > 0:
                target_protein = label_self_target(target_protein,feature_num)
                if feature_num != "":
                    self_targets.append([feature_num, target_protein])
                    self_targets.append(["downstream contig edge",""])         
    else:
        self_targets = [["----No genbank file", "skipped----"]]    
    return self_targets               
    
def Locus_annotator(align_locus,record,Cas_gene_distance,contig_Acc,protein_HMM_file,prefix,CDD=False):                   
    global all_contigs_checked
    global Cas_gene_analysis_dict
                   
    #If Cas_gene_distance is 0, this is a special case where all of the genbank sequences are to be checked in full for any Cas genes
    if Cas_gene_distance == 0:

        #Check to see if the current contig is part of a set that was already checked
        for check_list in all_contigs_checked:
            if contig_Acc in check_list[1]:
                proteins_identified, types_list, up_down = Cas_gene_analysis_dict[check_list[0]]
                break
        else:
            #will need to determine what all of the genbank files are, download them and search all of them for Cas genes
            #First, look up the assembly that the locus containing contig is in
            while True:
                genomes = NCBI_search(contig_Acc,"nucleotide",num_limit=100000,tag="",exclude_term="")
                assemblies = []
                assemblies = link_nucleotide_to_assembly(genomes,assemblies,num_limit=100000) 
                contig_GIs = link_assembly_to_nucleotide(assemblies,num_limit=100000,complete_only=False,num_genomes=0,complete_IDs=[],WGS_IDs=[])
                try:
                    genome_Accs = get_Accs(contig_GIs[0])
                    break
                except IndexError:  #these errors occasionally appear (from incomplete searches that get returned?)
                    print("Error looking up GenBank files for contigs from {0}'s assembly.".format(contig_Acc))
                    time.sleep(3)
            
            all_proteins_identified = []; all_types_list = []; total_up_down = 0
            for genome_Acc in genome_Accs:
                contig_filename = genome_Acc.split(".")[0] + ".gb"
                if os.path.isfile("GenBank_files/{0}.gb".format(contig_filename)):
                    try:
                        record = SeqIO.read(contig_filename, 'genbank')
                    except AttributeError:
                        record = download_genbank(genome_Acc)
                else:
                    record = download_genbank(genome_Acc)
                print("Checking {0} contig for Cas proteins...".format(genome_Acc))
                proteins_identified,types_list,up_down = find_Cas_proteins(genome_Acc,record,protein_HMM_file,prefix,CDD,Cas_gene_distance)  #align_pos would be first, only carried in this case to annotate protein location during search
                all_proteins_identified += proteins_identified
                all_types_list += types_list
                total_up_down += up_down
            proteins_identified = all_proteins_identified
            types_list = all_types_list
            up_down = total_up_down
            #Store the results from the genome scan so it will only be run once if multiple self-targeting spacers occurr in the same genome
            all_contigs_checked.append([genome_Accs[0],[genome_Accs]])
            Cas_gene_analysis_dict[genome_Accs[0]] = proteins_identified, types_list, up_down
        
    else:
        #Find Cas proteins near the spacer-repeat region
        proteins_identified,types_list,up_down = find_Cas_proteins(align_locus,record,protein_HMM_file,prefix,CDD,Cas_gene_distance)

    #Determine what Type the locus is
    Type = Type_check(types_list)
    
    #Determine whether the locus is complete
    Cas_search = locus_completeness_check(Type,proteins_identified)

    #Go through the list of proteins identified and remove synonomous proteins (e.g. Cas9/Csn1)
    #This is done by 
    
    renamed_proteins_identified = []
    for protein in proteins_identified:
        try:
            renamed_proteins_identified.append(protein + " ({0})".format(Cas_synonym_list[protein]))
        except KeyError:
            renamed_proteins_identified.append(protein)
    if renamed_proteins_identified != []:
        index = 0
        for name in renamed_proteins_identified:
            if name == '':
                renamed_proteins_identified.pop(index)  #remove the first blank position
            index += 1
                                                      
    #Handle the case that occurs if Type II-C (Type II-C can't be picked unless Cas9 is annotated with 'II-C')
    #Because Csn2 or Cas4 will automatically annotate as II-B or II-C, if all three are possible, must be II-C
    ##NOTE THIS ASSUMES THAT A TYPE II-B OR II-A LOCUS MISSING EITHER Csn2 or Cas4 is Type II-C!!!
    if "Type II-C" in Type and "Type II-A" not in Type and "Type II-B" not in Type:  #Will still allow a 'clean' Type II-C designation to be allowed.
        if "Csn2" not in Cas_search and 'Cas4' not in Cas_search:
            Type = "Presumed Type II-C"
    
    return Type,Cas_search,renamed_proteins_identified,types_list,up_down                            
 
def locus_re_annotator(imported_data,Cas_gene_distance,protein_HMM_file,repeat_HMM_file,prefix,CDD=False):
    
    print("Note! Genbank files are going to be downloaded. Remove them after if unwanted.")
    re_analyzed_data = []
    for result in imported_data:
        contig_Acc = result[2]  #locus Acc number
        align_locus = result[11]  #position of the self_targeting spacer in the CRISPR locus  
        print("Reanalyzing locus found in {0}...".format(contig_Acc))
        contig_filename = contig_Acc.split(".")[0] + ".gb"
        if os.path.isfile("GenBank_files/{0}.gb".format(contig_filename)):
            record = SeqIO.read(contig_filename, 'genbank')
        else:
            record = download_genbank(contig_Acc)
        
        Type_proteins,Cas_search,proteins_identified,types_list,up_down = Locus_annotator(align_locus,record,Cas_gene_distance,contig_Acc,protein_HMM_file,prefix,CDD)
        
        #Convert the Cas protein search results (and Cas genes found) into a printable string       
        if len(Cas_search) > 1:
            locus_condition = "".join(Cas_search[:2])
            if len(Cas_search) > 2:
                locus_condition += ", " + ", ".join(Cas_search[2:])
        else:  
            locus_condition = Cas_search[0]
        try:
            if len(proteins_identified) > 1:
                proteins_found = ", ".join(proteins_identified[:])
            elif len(proteins_identified) == 1:
                proteins_found = proteins_identified[0]
            else:
                proteins_found = 'None'
        except UnboundLocalError:
            proteins_found = 'N/A'
        
        repeat_direction,Type_repeat,possible_types = repeat_HMM_check(result[16],prefix,repeat_HMM_file)
        
        #Double check the direction of the array, and flip the spacer/repeat/PAM sequences if in reverse
        #First, determine the array direction based on the Cas gene places
        if repeat_direction == 0:
            array_direction = "CRT assumed forward, orientation unknown"; extra_details = "no predictions"
            #Check to see where the Cas proteins are relative to the array and where they are expected based on the predicted type (prefer Cas protein annotation)
            #First figure out if either Type picks a single Type
            if Type_proteins == "?" and Type_repeat != "Repeat not recognized":
                types_to_use = possible_types
                extra_details = "repeat sequence"
            elif "or" in Type_proteins and "or" not in Type_repeat and "?" not in Type_repeat and "Repeat not recognized" not in Type_repeat:   
                #Only one type determined by repeats, but multiple from proteins
                types_to_use = possible_types
                extra_details = "repeat sequence"
            elif "or" in Type_proteins and "or" in Type_repeat:   
                #Both predict multiple possible types, default to those predicted by the proteins
                #extract the types predicted in Type_proteins
                extra_details = "Cas proteins"
            elif Type_proteins != "?":
                #1 or more types predicted by the proteins 
                extra_details = "Cas proteins"
            if extra_details == "Cas proteins":
                if Type_proteins == "?":
                    #determine if too many types or none to make a call
                    if types_list == []:
                        extra_details = "no predictions"  #Reset to default, since there is no way to predict a Cas type
                    else:
                        #collapse the list of possible types
                        types_to_use = [x.split()[1] for x in list(set(types_list))]  #remove the word 'Type'
                else:
                    types_to_use = []
                    for string in Type_proteins.split():
                        if "-" in string:
                            if string[-1] in (",", "?"):
                                types_to_use.append(string[:-1])
                            elif "-----" not in string:
                                types_to_use.append(string)
            if extra_details != "no predictions":
                #Now Check the possible types to see what the direction is (Note! presumed Type II-C will come out as backward)
                directions_predicted = []
                for dir_check in types_to_use:
                    directions_predicted.append(Expected_array_directions["Type {0}".format(dir_check)])
                #Confirm they are all in the same directions
                expected_direction = directions_predicted[0]
                for el in directions_predicted:
                    if el != expected_direction:
                        #disagreement, reset to unknown direction
                        expected_direction = 0
                        break
                #Now determine if the array orientation matches the expected orientation        
                if up_down > 0:  #if the Cas genes precede the array
                    up_down = 1
                elif up_down < 0:
                    up_down = -1
                if expected_direction != 0:
                    if up_down == expected_direction:
                        repeat_direction = 1   #already in correct orientation
                    else:
                        repeat_direction = -1  #needs to be flipped
        else:
            extra_details = "repeat sequence"
            if repeat_direction > 0:
                array_direction = "Original orientation correct (determined with {0})".format(extra_details)
            elif repeat_direction < 0:
                array_direction = "Original orientation wrong (sequences reversed, determined with {0})".format(extra_details)
        
        #if the repeat_direction is found to be backward, do the flipping
        if repeat_direction < 0:
            #Need to flip spacer sequence, PAM sequences, consensus Repeat
            PAM_seq_up = str(Seq(result[13]).reverse_complement())           
            temp_seq = PAM_seq_up
            PAM_seq_up = str(Seq(result[15]).reverse_complement())    
            PAM_seq_down = temp_seq          
            consensus_repeat = str(Seq(result[16]).reverse_complement())                
            spacer_seq = str(Seq(result[12]).reverse_complement())                
            array_direction = "Original orientation wrong (sequences reversed, determined with repeat sequence)"
        
            #Also need to flip the orientation of the mutation annotations (for the repeats and target sequence)
            target_sequence = result[14]
            if target_sequence != "Perfect match":
                target_sequence = flip_mismatch_notation(result[14])        
            repeat_mutations = result[17]
            if repeat_mutations not in ("None","Skipped","Error in repeat, not analyzed"):
                #need to parse out the upper and lower mutations
                if result[17][:4] == "Both":
                    repeat_U = result[17].split(": ")[-2].split(", ")[0]
                    repeat_D = result[17].split(": ")[-1].strip()
                elif result[17][:4] == "Down":
                    repeat_U = ""
                    repeat_D = result[17].split(": ")[-1].strip()
                elif result[17][:4] == "Upst":
                    repeat_U = result[17].split(": ")[-1].strip()
                    repeat_D = ""
                if repeat_U != "":
                    repeat_U = flip_mismatch_notation(repeat_U)
                if repeat_D != "":
                    repeat_D = flip_mismatch_notation(repeat_D)                
                repeat_mutations = target_mutation_annotation(repeat_U, repeat_D)
            flipped_fields = [spacer_seq,PAM_seq_up,target_sequence,PAM_seq_down,consensus_repeat,repeat_mutations,array_direction]
        else:
            flipped_fields = result[12:19]  #the original, unflipped data
        
        re_analyzed_data.append(result[:4] + [Type_proteins,Type_repeat,locus_condition,proteins_found] + result[8:12] + flipped_fields + result[19:])
    
    return re_analyzed_data                                                                                                                                                                                                                                                         

                                                                 
def repeat_HMM_check(consensus_repeat,prefix,repeat_HMM_file):
    
    #Determine the orientation of the array. First try to align the repeat, then look for Cas proteins nearby and assume that the Cas proteins are upstream
    #Check the consensus repeat against the HMM list
    
    with open("{0}temp/consensus_repeat.fa".format(prefix), 'w') as file1:
        file1.write(">consensus_repeat\n{0}\n".format(consensus_repeat))
    hmm_cmd = "{0}nhmmscan -E 1e-6 --noali {1} {2}temp/consensus_repeat.fa ".format(bin_path,repeat_HMM_file,prefix)
    handle = subprocess.Popen(hmm_cmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    output, error = handle.communicate()
    if error != '':
        print("Error in HMMscan for repeats\n", error)
        sys.exit()        
    
    #Parse the output to find the direction of the alignment (if there was one)
    Type_repeat = "Repeat not recognized"; repeat_direction = 0; possible_types = []
    expression1 = re.compile("\s+E-value\s+score\s+bias")   #find the table labels for the data
    for line in output.split('\n'):
        a = re.search(expression1, line)
        if a is not None: 
            i = 2
            e_value = 1
            while True:
                data_string = output.split('\n')[output.split('\n').index(line) + i]  #Get the data from lines below
                i += 1
                if data_string == "": #No hits found
                    break
                try:
                    found_e_value = float(data_string.strip().split()[0])
                    if found_e_value < e_value:  #want to take the lowest e-value (best match)
                        e_value = found_e_value
                        repeat_group = data_string.strip().split()[3]  #The repeat group is the 4th position
                        repeat_direction = int(data_string.strip().split()[5]) - int(data_string.strip().split()[4]) #positive means CRT and HMM direction match
                        #Use the identified group to guess at the Type
                        if repeat_group[-1] == 'R':  #Removes the R designation that was added to indicate where the original REPEATS data was backward
                            repeat_group = repeat_group[:-1]
                        possible_types = Repeat_families_to_types[repeat_group]
                        if len(possible_types) == 1:
                            Type_repeat = "Type {0}".format(possible_types[0])
                        elif len(possible_types) == 2:
                            Type_repeat = "Type {0} or {1}".format(possible_types[0],possible_types[1])
                        elif len(possible_types) > 2:
                            Type_repeat = "Type" + "".join([" {0},".format(string) for string in possible_types[:-1]]) + " or {0}".format(possible_types[-1])
                        Type_repeat += " (group {0})".format(repeat_group)
                except:
                    break
            break
                                                                      
    return repeat_direction,Type_repeat,possible_types                                                         
                                                                                                                               
                                                                 # (contig with self-target, WGS-master -str, # of contig from top -int)
def analyze_target_region(spacer_seq,fastanames,Acc_num_self_target,Acc_num,self_target_contig,alt_alignment,align_locus,direction,crispr,spacer,locus_Accs,provided_dir,genome_type,Cas_gene_distance,affected_genomes,alt_align_subtract,bin_path,protein_HMM_file,repeat_HMM_file,prefix,CDD=False,repeats=4):

    #Determine whether the current contig (or genome) has already had it's locus checked
    global loci_checked
    
    if genome_type == 'WGS':
        contig_Acc = locus_Accs[Acc_num+Acc_num_self_target+str(align_locus)] 
    else:
        contig_Acc = Acc_num
    
    #First check whether this array has been checked once before
    print("Analyzing self-targeting spacer found in {0}...".format(Acc_num_self_target))
    false_positive = False
    try:
        species,Type_proteins,Type_repeat,proteins_identified,Cas_search,array_direction,false_positive = loci_checked[contig_Acc + "-" + str(crispr)] 
        need_locus_info = False  
    except KeyError:    #Hasn't been made yet or not found
        need_locus_info = True    #Need to determine the information and add to the dictionary

    if false_positive:
        return ["" for x in range(0,15)] + [True] #return a blank set to calling function, essentially 'skipping' this array (it won't be included after anyway)
    else:
        #Get the sequence for the contig (or genome) containing the self-targeting spacer match
        sequence,fastaname = fetch_sequence(fastanames,Acc_num,self_target_contig,provided_dir)
        if need_locus_info:
            #Download the genbank file
            record = download_genbank(contig_Acc)
            if type(record) is not str:
                #Get the species name
                species = record.description.split(",")[0]
                if genome_type == "WGS":
                    for word in ("contig","Contig","genomic scaffold","scaffold"):
                        species = species.split(word)[0] 
                    #species = record.features[0].qualifiers["organism"][0]
                    #if genome_type == 'complete':
                    #    species += record.features[0].qualifiers["strain"][0]
                Type_proteins,Cas_search,proteins_identified,types_list,up_down = Locus_annotator(align_locus,record,Cas_gene_distance,contig_Acc,protein_HMM_file,prefix,CDD) 
            else:
                species = "Missing genbank formatted data"; Type_proteins = "?"; proteins_identified = ['-----']; Cas_search = ['-----']; up_down = 0; types_list = []
            loci_checked[contig_Acc + "-" + str(crispr)] = [species,Type_proteins,proteins_identified,Cas_search] 

        #Going to figure out what the consensus repeat is and if there are mutations in it.
        consensus_repeat = "Skipped"
        repeat_mutations = "Skipped"
        
        #First determine the consensus repeat
        #Open the CRISPR results file and collect all of the repeat and spacer sequences
        with open("{0}CRISPR_analysis/".format(prefix)+Acc_num.split('.')[0]+'.out') as file1:
            lines = file1.readlines()    
        expression1 = re.compile("CRISPR\s{0}".format(crispr))  #Regular expression to match: CRISPR XX to find correct array
        found_array = False; record = False; repeats = []; spacers = []
        for line in lines:
            a = expression1.match(line)
            if a is not None:
                found_array = True
            if found_array and line[:7] == "-"*7:
                record = not record
                if repeats != []:   #at the end of the list
                    break
                continue
            if record:
                repeats.append(line.split()[1])
                try:
                    spacers.append(line.split()[2])
                except IndexError:
                    pass  #there's one less spacer than repeats
        
        #Look for false positives and incorrect repeat/spacers
        #Begin by performing a multiple sequence alignment for the spacers, looking for hotspots on either end that could indicate a misplaced repeat part
        i = 1; fasta_string = ''; valid_dna = 'ACGTN'; 
        for spaceri in spacers:
            if all(i in valid_dna for i in spaceri) and len(spaceri) > 10:  #Check if the repeat has an unexpected character (not A,C,G,T,N), and that it's not a single/short string
                fasta_string += '>{0}\n{1}\n'.format(i,spaceri)
                i += 1
        clustal_cmd = "{0}clustalo -i - --force --outfmt=clustal -o {1}temp/align_temp_spacer_output.aln".format(bin_path,prefix)      
        handle = subprocess.Popen(clustal_cmd.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        output, error = handle.communicate(input=fasta_string)                        
        alignment = AlignIO.read("{0}temp/align_temp_spacer_output.aln".format(prefix), "clustal")
        spacers_align = AlignInfo.SummaryInfo(alignment)
        consensus_spacer = spacers_align.dumb_consensus()  
        spacers_pssm = spacers_align.pos_specific_score_matrix(consensus_spacer, chars_to_ignore = ['N'])
        #Now start at the beginning of the spacer consensus and step forward looking for overrepresented bases
        if len(spacers) > 4:
            overrep_percent = 0.75 #This number represents what the cutoff is for indentifying mistakes in the repeats - heuristic
        else:
            overrep_percent = 1   #to prevent small arrays from getting caught when they happen to have similar spacers sequences
        move_F_len = 0; move_R_len = 0; indexes = range(0,len(consensus_spacer)-1)
        for step_dir in (1, -1):
            if step_dir == -1:
                reversed(indexes)
            for i in indexes:  #will step forward then backward to look for mischaracterized repeats -1 because the last nucleotide tends to be more variable
                total_counts = len(spacers)   #edit to include gaps in the count for representation
                count_limit = overrep_percent * total_counts
                if round(count_limit) < count_limit:
                    count_limit = round(count_limit) + 1  #always round up
                else:
                    count_limit = round(count_limit)
                strong_homology = False
                for base in ("A","T","G","C"):
                    try:
                        base_count = spacers_pssm[i][base]
                        if base_count >= count_limit:
                            if step_dir > 0:
                                move_F_len += 1
                            else:
                                if move_R_len == 0:
                                    move_R_len += 1
                                move_R_len += 1
                            strong_homology = True
                            break
                    except KeyError:  #this can occur if the PSSM doesn't have one of the letters in the alignment
                        pass
                if not strong_homology:
                    break
                      
        #Next, if either move statistic is greater than 0, remake the spacers and repeats lists with the correct sequences
        repeats_temp = []; i = 0
        for repeat in repeats:
            if i == 0: 
                repeats_temp.append(repeat + spacers[i][:move_F_len])              
            elif i < len(spacers): 
                repeats_temp.append(spacers[i-1][len(spacers[i-1])-move_R_len:len(spacers[i-1])] + repeat + spacers[i][:move_F_len])
            else:
                repeats_temp.append(spacers[i-1][len(spacers[i-1])-move_R_len:len(spacers[i-1])] + repeat)
            i += 1
        
        repeats = repeats_temp
        spacers_temp = []
        for spaceri in spacers:
            spacers_temp.append(spaceri[move_F_len:len(spaceri)-move_R_len-1])
        spacers = spacers_temp
        
        #Do a check to see if it's false positive (direct repeat for example). If most of the spacers are now under the min length cutoff (from too much homology)
        i = 0 
        for spaceri in spacers:
            if len(spaceri) < 18:
                i += 1
        if i >= 0.25 * len(spacers):  #If 25% of the corrected spacers are under 18, reject as a false array
            false_positive = True    
            loci_checked[contig_Acc + "-" + str(crispr)] = ["Missing genbank formatted data","","","","","",false_positive]
            print("CRISPR array {0} in {1} does not appear to be an array upon re-analysis, skipping...".format(crispr,Acc_num))
            return ["" for x in range(0,15)] + [True]  
        
        if not false_positive:
            #Adjust the known spacer 
            if move_F_len + abs(move_R_len) > 0 :
                print("CRISPR array {0} in {1} detected by CRT found to be maligned, correcting...".format(spacer,Acc_num))
                spacer_seq = spacer_seq[move_F_len:len(spacer_seq)-move_R_len-1]
                #Also adjust the alignment positions
                align_locus = align_locus + move_F_len
                alt_alignment = alt_alignment + move_F_len
                if move_F_len != 0:
                    #need to adjust the keys in locus_Accs (used for correct labeling of the contig with the CRISPR array)
                    locus_Accs[Acc_num+Acc_num_self_target+str(align_locus)] = locus_Accs[Acc_num+Acc_num_self_target+str(align_locus-move_F_len)]
                
            #Perform a multiple sequence alignment to get the consensus repeat using dummy alignment from biopython
            #Build a fasta format
            i = 1; fasta_string = ''; valid_dna = "ACGTN"; spacer_pos_hold = spacer
            for repeat in repeats:
                if all(i in valid_dna for i in repeat) and len(repeat) > 10:  #Check if the repeat has an unexpected character (not A,C,G,T,N), and that it's not a single/short string
                    fasta_string += '>{0}\n{1}\n'.format(i,repeat)
                    i += 1
                elif spacer >= i: 
                    spacer_pos_hold -= 1  #If one of the repeats is removed due to being too short, etc. this variable is used to change the spacer position below to check the appropriate repeats
            if not os.path.exists('{0}temp'.format(prefix)):
                os.mkdir('{0}temp'.format(prefix))
            clustal_cmd = "{0}clustalo -i - --force --outfmt=clustal -o {1}temp/align_temp_output.aln".format(bin_path,prefix)
            handle = subprocess.Popen(clustal_cmd.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            output, error = handle.communicate(input=fasta_string)                        
            try:
                alignments = AlignIO.read("{0}temp/align_temp_output.aln".format(prefix), "clustal")
                repeats_align = AlignInfo.SummaryInfo(alignments)
                consensus_repeat = str(repeats_align.dumb_consensus(ambiguous='N', require_multiple=1))                 
            
                #Then find up and downstream mutations, Switch to a symbolic representation for easier viewing
                downstream = False; 
                for repeat in (str(alignments[spacer_pos_hold-1].seq),str(alignments[spacer_pos_hold].seq)):
                    i = 0; repeat_temp = ''
                    if repeat != consensus_repeat:
                        for letter in repeat:
                            if letter == consensus_repeat[i] or consensus_repeat[i] == 'N':  #perfect match
                                repeat_temp += "."
                            elif consensus_repeat[i] == '-' or letter == '-':   #case where there's an insertion in the repeat
                                repeat_temp += letter
                            elif letter != consensus_repeat[i]:  #don't match, but no dash means a mismatch
                                repeat_temp += letter.lower()    #This way a mutation is lowercase, an insertion is uppercase
                            i += 1
                    if repeat_temp == len(repeat) * '.':
                        repeat_temp = ''  #catches case where an internal N prevents a perfect match
                    if downstream:
                        repeat_D = repeat_temp
                    else:
                        repeat_U = repeat_temp
                    downstream = True
                repeat_mutations = target_mutation_annotation(repeat_U, repeat_D)
            except IndexError: #will only occur if the last repeat has strange characters
                print("Issue with a repeat annotation from CRT. Skipping repeat mutation analysis of {0}...".format(Acc_num))
                repeat_mutations = "Error in repeat, not analyzed"

            #Take the spacer sequence and realign to the target to find what part of the sequence is perfectly aligned to establish a register
            query_file = "{0}temp/temp_query.txt".format(prefix)
            with open(query_file, "w") as file1:
                file1.write(">Query_Sequence\n{0}\n".format(spacer_seq))
            #Then write the subject file with a subsequence near the aligned position
            pad_size = len(spacer_seq) + 10
            lower = max(alt_alignment-pad_size,0)  #adjust for padding making an index that goes off the edge of the contig
            upper = min(alt_alignment+len(spacer_seq)+pad_size,len(sequence))
            target_subseq = sequence[lower:upper]   #creates a subsequence to search where the target is known to occur with some padding
            if direction < 1:  #always makes alignment in the same direction
                target_subseq = str(Seq(target_subseq).reverse_complement())
            subject_file = "{0}temp/temp_subject.txt".format(prefix)
            with open(subject_file, "w") as file1:
                file1.write(">Subject_Sequence\n{0}\n".format(target_subseq))
 
            output_format = 6   #originally coded with output format 4, but doesn't allow for as rigid control of single alignments
            #Then align the spacer sequence to the subsection
            blast_cmd = "{0}blastn -query {1} -subject {2} -outfmt {3} -max_target_seqs 1 -word_size 7 -ungapped -strand plus".format(bin_path,query_file,subject_file,output_format)
            handle = subprocess.Popen(blast_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
            output, error = handle.communicate()
            #Now look up what part of the spacer aligns, and extend the alignment in both directions
            #Because CRISPR alignment will not allow for indels, assume that stuck in register of best alignment
            #In reality, one end or the other of the spacer will be more important, but the best alignment is not in the same register as the PAM/seed region, it probably can't bind anyway
            
            #Used for output format 4
            if output_format == 4:
                expression1 = re.compile("Query_\d+")
                expression2 = re.compile("Subject_\d+")
                for line in output.split('\n'):
                    a = expression1.match(line)
                    if a is not None:
                        ext_lower = int(line.split()[1]) - 1
                        ext_upper = len(spacer_seq) - int(line.split()[3])
                    b = expression2.match(line)
                    #Find the alignment in the subject, and extend either way to get the whole string
                    if b is not None:
                        s_lower = int(line.split()[1]) - ext_lower - 1 #1 is added for indexing adjustment (1 -> 0)
                        s_upper = int(line.split()[3]) + ext_upper
                        break
            elif output_format == 6:
                expression1 = re.compile("Query_")
                for line in output.split('\n'):
                    a = expression1.match(line)
                    if a is not None:
                        ext_lower = int(line.split('\t')[6]) - 1
                        ext_upper = len(spacer_seq) - int(line.split('\t')[7])
                        s_lower = int(line.split('\t')[8]) - ext_lower - 1 #1 is added for indexing adjustment (1 -> 0)
                        s_upper = int(line.split('\t')[9]) + ext_upper
                        break
            
            #Take the gapless alignment and get the full subject subsequence
            if s_lower < 0 and s_upper > len(target_subseq):
                subject_subseq = target_subseq[0:len(target_subseq)]
            elif s_lower < 0:
                subject_subseq = target_subseq[0:s_upper]
            elif s_upper > len(target_subseq):
                subject_subseq = target_subseq[s_lower:len(target_subseq)]
            else:
                subject_subseq = target_subseq[s_lower:s_upper]
            
            #Then stepwise compare the strings for mismatches (check not perfect match first)
            letter_pos = 0; target_sequence = ''
            if subject_subseq == spacer_seq:
                target_sequence = 'Perfect match'
            else:
                if len(spacer_seq) == len(subject_subseq):  #Check they are the same length, if not, on the edge of a contig
                    for q_letter in spacer_seq.lower():
                        s_letter = subject_subseq[letter_pos].lower()
                        if q_letter != s_letter:
                            target_sequence += s_letter
                        else:
                            target_sequence += '.'
                        letter_pos += 1
                else: 
                    fast_forward = 0
                    while s_lower < 0:
                        target_sequence += 'x'
                        s_lower += 1; fast_forward += 1
                    for q_letter in spacer_seq[fast_forward:].lower():
                        try:
                            s_letter = subject_subseq[letter_pos].lower()
                            if q_letter != s_letter:
                                target_sequence += s_letter
                            else:
                                target_sequence += '.'
                        except IndexError:
                            #will occur if the edge of the contig is on the 3' side
                            target_sequence += 'x'
                        letter_pos += 1
            #Now get the correct PAM sequences from the adjusted subject target sequence 
            PAM_seq_up = target_subseq[s_lower-9:s_lower]
            PAM_seq_down = target_subseq[s_upper:s_upper+9]
            
        #Use the consensus repeat to try to gain information about the array
        repeat_direction,Type_repeat,possible_types = repeat_HMM_check(consensus_repeat,prefix,repeat_HMM_file)
        
        #Here, we'll double check the direction of the array, and flip the spacer/repeat/PAM sequences if in reverse
        #First, determine the array direction based on the Cas gene places
        if repeat_direction == 0 and need_locus_info:
            array_direction = "CRT assumed forward, orientation unknown"; extra_details = "no predictions"
            #Check to see where the Cas proteins are relative to the array and where they are expected based on the predicted type (prefer Cas protein annotation)
            #First figure out if either Type picks a single Type
            if Type_proteins == "?" and Type_repeat != "Repeat not recognized":
                types_to_use = possible_types
                extra_details = "repeat sequence"
            elif "or" in Type_proteins and "or" not in Type_repeat and "?" not in Type_repeat and "Repeat not recognized" not in Type_repeat:   
                #Only one type determined by repeats, but multiple from proteins
                types_to_use = possible_types
                extra_details = "repeat sequence"
            elif "or" in Type_proteins and "or" in Type_repeat:   
                #Both predict multiple possible types, default to those predicted by the proteins
                #extract the types predicted in Type_proteins
                extra_details = "Cas proteins"
            elif Type_proteins != "?":
                #1 or more types predicted by the proteins 
                extra_details = "Cas proteins"
            if extra_details == "Cas proteins":
                if Type_proteins == "?":
                    #determine if too many types or none to make a call
                    if types_list == []:
                        extra_details = "no predictions"  #Reset to default, since there is no way to predict a Cas type
                    else:
                        #collapse the list of possible types
                        types_to_use = [x.split()[1] for x in list(set(types_list))]  #remove the word 'Type'
                else:
                    types_to_use = []
                    for string in Type_proteins.split():
                        if "-" in string:
                            if string[-1] in (",", "?"):
                                types_to_use.append(string[:-1])
                            elif "-----" not in string:
                                types_to_use.append(string)
            if extra_details != "no predictions":
                #Now Check the possible types to see what the direction is (Note! presumed Type II-C will come out as backward)
                directions_predicted = []
                for dir_check in types_to_use:
                    directions_predicted.append(Expected_array_directions["Type {0}".format(dir_check)])
                #Confirm they are all in the same direction
                expected_direction = directions_predicted[0]
                for el in directions_predicted:
                    if el != expected_direction:
                        #disagreement, reset to unknown direction
                        expected_direction = 0
                        array_direction = "Predicted Types have conflicting orientations"
                        break
                #Now determine if the array orientation matches the expected orientation        
                if up_down > 0:  #if the Cas genes precede the array
                    up_down = 1
                elif up_down < 0:
                    up_down = -1
                if expected_direction != 0:
                    if up_down == expected_direction:
                        repeat_direction = 1   #already in correct orientation
                        array_direction = "CRT orientation correct (determined with {0})".format(extra_details)
                    else:
                        repeat_direction = -1  #needs to be flipped
                        array_direction = "CRT orientation wrong (sequences reversed, determined with {0})".format(extra_details)
        else:
            extra_details = "repeat sequence"
            if repeat_direction > 0:
                array_direction = "CRT orientation correct (determined with {0})".format(extra_details)
            elif repeat_direction < 0:
                array_direction = "CRT orientation wrong (sequences reversed, determined with {0})".format(extra_details)
        #If there is a consensus direction, and it's backward, flip the array
        if repeat_direction < 0:
            #Need to flip spacer sequence, PAM sequences, consensus Repeat
            PAM_seq_up = str(Seq(PAM_seq_up).reverse_complement())           
            temp_seq = PAM_seq_up
            PAM_seq_up = str(Seq(PAM_seq_down).reverse_complement())    
            PAM_seq_down = temp_seq          
            consensus_repeat = str(Seq(consensus_repeat).reverse_complement())                
            spacer_seq = str(Seq(spacer_seq).reverse_complement())                
            
            #Also need to flip the orientation of the mutation annotations (for the repeats and target sequence)
            if target_sequence != "Perfect match":
                target_sequence = flip_mismatch_notation(target_sequence)        
            if repeat_mutations not in ("None","Skipped","Error in repeat, not analyzed"):
                if repeat_U != "":
                    repeat_U = flip_mismatch_notation(repeat_U)
                if repeat_D != "":
                    repeat_D = flip_mismatch_notation(repeat_D)                
                repeat_mutations = target_mutation_annotation(repeat_U, repeat_D)
                                    
        #if the validity of the locus hasn't been determined yet, include the information
        if len(loci_checked[contig_Acc + "-" + str(crispr)]) < 5:
            try:
               loci_checked[contig_Acc + "-" + str(crispr)] = [species,Type_proteins,Type_repeat,proteins_identified,Cas_search,array_direction,false_positive]
            except UnboundLocalError:
               loci_checked[contig_Acc + "-" + str(crispr)] = ["Missing genbank formatted data","","","","",array_direction,false_positive]
        
        #One other way to check for false positives is to examine the PAM sequences
        #If a false positive, either PAM sequence may align with either end of the consensus sequence
        #NOTE: this will NOT throw out the whole array, but only skip this spacer
        #Here, check for an 8/9 match of the PAM sequence (upstream PAM matches 3' end of repeat, downstream PAM matches 5') - this corresponds to a ~1/65000 random chance of occurring
        errors_allowed = 1; pos = 0; errors_accum = 0
        for PAM_seq in (PAM_seq_down,PAM_seq_up):
            if pos == 0:
                consensus_r = consensus_repeat[:9]
            else:
                consensus_r = consensus_repeat[-9:]
                pos = 0; errors_accum = 0
            for letter in consensus_r:
                try:
                    if letter == PAM_seq[pos]:
                        errors_accum += 1
                except IndexError:
                    break
                if errors_accum >= 9 - errors_allowed:  #if 8/9 match, reject
                    print("Spacer {0} in CRISPR array {1} appears to be a false-positive (PAM matches repeat), skipping...".format(spacer, crispr))
                    return ["" for x in range(0,15)] + [True]   #The false here will cause the spacer to be skipped, but not record the array as a false in case other spacers in the array are ok.
                pos += 1        
        
        #May need to adjust the alt_alignment length if there are Ns masked from CRT
        #NOTE: this needs to be correcteed later because 
        try:
            Ns_removed = affected_genomes[Acc_num]  #this will give a key error if the genome isn't Ns masked
            alt_alignment = correct_spacers_for_Ns(alt_alignment,Ns_removed,alt_align_subtract,False)
        except KeyError:  #if not an affected genome
            pass 
        
        #Now search the genbank files to see what the self-targeting gene is and look up if hypothetical
        self_targets = find_spacer_target(Acc_num_self_target,alt_alignment)
                                                                                                                                                                                       
        #Convert self-targeting information into a printable string
        if len(self_targets) == 1:
            self_target = ", ".join(self_targets[0])
        elif len(self_targets) == 2:
            self_target = "Between " + ", ".join(self_targets[0]) + " & " + ", ".join(self_targets[1])   
        elif len(self_targets) == 0:
            self_target = 'No features in DNA'
        else:
            self_target = ''
            #for listx in self_target:
            #    self_target = self_target + ", ".join(self_targets[0]) + " & "
            #self_target = self_target[:-3]       #remove any trailing ampersands                    
        
        #Convert the Cas protein search results (and Cas genes found) into a printable string       
        if len(Cas_search) > 1:
            locus_condition = "".join(Cas_search[:2])
            if len(Cas_search) > 2:
                locus_condition += ", " + ", ".join(Cas_search[2:])
        else:  
            locus_condition = Cas_search[0]
        try:
            if len(proteins_identified) > 1:
                proteins_found = ", ".join(proteins_identified[:])
            elif len(proteins_identified) == 1:
                proteins_found = proteins_identified[0]
            else:
                proteins_found = 'None'
        except UnboundLocalError:
            proteins_found = 'N/A'
                                                                        
        return PAM_seq_up,PAM_seq_down,species,Type_proteins,Type_repeat,locus_condition,proteins_found,self_target,consensus_repeat,repeat_mutations,spacer_seq,alt_alignment,align_locus,array_direction,target_sequence,false_positive

def correct_spacers_for_Ns(spacer_pos,Ns_removed,contig_start,align_locus_correction = False):
    
    corrected_Ns_removed = []
    for Ns in Ns_removed:
        corrected_Ns_removed.append([Ns[0]-contig_start,Ns[1]])
    
    #Need to add the number of Ns removed upstream of the spacer position to its position value
    adjust_val = 0
    if align_locus_correction:
        position = spacer_pos - contig_start
    else:
        position = spacer_pos
    for line in corrected_Ns_removed:
        if position >= line[0] >= 0:
            adjust_val += line[1] 
        elif line[0] >= 0:
            break
    spacer_pos += adjust_val 
           
    return spacer_pos
       
def flip_mismatch_notation(sequence):
    
    temp1 = sequence[::-1]
    temp2 = ''
    for base in temp1:
        if base == 'a':
            temp2 += 't'
        elif base == 't':
            temp2 += 'a'
        elif base == 'c':
            temp2 += 'g'                    
        elif base == 'g':
            temp2 += 'c'            
        else:
            temp2 += base
    sequence = temp2   
    
    return sequence             

def target_mutation_annotation(repeat_U, repeat_D):

    if repeat_D == '' and repeat_U == '':
        repeat_mutations = 'None'
    elif repeat_D == '' and repeat_U != '':
        repeat_mutations = 'Upstream repeat mutated: {0}'.format(repeat_U)
    elif repeat_D != '' and repeat_U == '':
        repeat_mutations = 'Downstream repeat mutated: {0}'.format(repeat_D)
    else:             
        repeat_mutations = 'Both repeats mutated: Upstream: {0}, Downstream: {1}'.format(repeat_U,repeat_D)

    return repeat_mutations                            

def self_target_analysis(blast_results,spacer_data,pad_locus,fastanames,provided_dir,Cas_gene_distance,affected_genomes,bin_path,protein_HMM_file,repeat_HMM_file,prefix,CDD,repeats=4):

    #Next, search each genome sequence for each repeat sequence and determine if it shows up more than once (bypassed CRISPR)
    #Since the genomes, spacers, etc. are in the same order, look for the start lengths and filter out reads that were found from CRISPR search
    
    #First, build a dictionary containing the contigs of each genome
    contig_Accs = {}
    for key, value in fastanames.items():
        contig_list = []
        filetocheck = value[0]
        with open(filetocheck, 'r') as file1:
            lines = file1.readlines()
        for line in lines:
            if line[0] == '>':
                try:
                    contig_list.append(line.split("|")[1].strip())
                except:
                    contig_list.append(line.split(" ")[0].replace(">","").strip())  #skip the opening caret
        contig_Accs[key] = contig_list
    
    blast_results_filtered_summary = []
    genome_number = 0
    locus_Accs = {}
    Acc_num = '';  Acc_num_self_target = ''
    for genome in blast_results:
        for result in genome:
            genome_type = spacer_data[genome_number][0][2]
            handle = [x.strip() for x in result.split("\t") if x != '']
            if handle != []:
                alt_alignment = int(handle[8]) #position of CRISPR alignment (may or may not be in locus)  FROM BLAST
                direction = int(handle[9])-int(handle[8]) #If negative, it's on the negative strand
                if spacer_data[genome_number][0][1] == 'lookup' and genome_type == 'complete':   ##This only works becasue index numbering still matches, will not after this block 
                    Acc_num = handle[1].strip()   #Accession number for genome used
                    Acc_num_self_target = Acc_num           #Acc_num_self_target no longer used
                elif spacer_data[genome_number][0][1] == 'lookup' and genome_type == 'WGS':   #Formatting in-house and dictated above
                    Acc_num_self_target = handle[1].split("|")[1]   #Accession number for contig of found spacer (not necessarily locus)!
                    Acc_num = handle[1].split("|")[0]   #Not GI number!! Accession of master WGS record!
                elif spacer_data[genome_number][0][1] == 'provided' and genome_type == 'complete':  
                    try:  #try to see if has regular NCBI header
                        Acc_num = handle[1].strip()   #Accession number for genome used
                        Acc_num_self_target = Acc_num   
                    except:
                        Acc_num = handle[1].strip()  #store the name this way if sequence was provided
                        Acc_num_self_target = Acc_num
                else:   ##If provided and WGS
                    try:  #try to see if has an NCBI header formatted for the contigs
                        Acc_num_self_target = handle[1].split("|")[1]   #Accession number for contig of found spacer (not necessarily locus)!
                        Acc_num = handle[1].split("|")[0]   #Not GI number!! Accession of master WGS record!
                    except:
                        #Getting here suggests that the genome does not have the master|contig format, so will try to find the master using the contig_Accs
                        try:
                            Acc_num_self_target = handle[1].strip().split(" ")[0]  #try to store the name this way if sequence was provided
                            #Acc_num = Acc_num_self_target
                            for key,value in contig_Accs.items():  #try a reverse dictionary lookup to find the WGS master
                                if Acc_num_self_target in value:
                                    Acc_num = key
                        except KeyError:
                            Acc_num = handle[1].strip()  #If cannot get any formatting found, just pass the line along, but this is likely to cause a problem later. 
                            Acc_num_self_target = Acc_num
                            print("Warning! {0} does not have a readily identifable Accession number, results may be incorrect!".format(Acc_num))
                
                crispr = int(handle[0].split("_")[1])
                spacer = int(handle[0].split("_")[3]) 
                spacer_seq = spacer_data[genome_number][crispr][spacer][0]
                #search data for GI, then CRISPR/spacer combination, then see if the position is the previously determined
                
                for x in spacer_data:
                    outside_loci = True
                    if x[0][0] == Acc_num:
                        #Check that the spacer is not occurring in one of the loci that was predicted
                        try:
                            align_locus = x[crispr][spacer][1] #Position of CRISPR spacer in locus (curr_spacer_pos assigns this above)
                        except:
                            print(align_locus)
                            print(x)
                        if genome_type == 'complete':
                            alt_align_subtract = 0  #placeholder
                            for locus in range(1,len(x)):
                                locus_range = [int(y) for y in x[locus][0].split("Range: ")[1].strip().split(" - ")]
                                if locus_range[0] - pad_locus <= alt_alignment <= locus_range[1] + pad_locus:  #if falls within any locus
                                    outside_loci = False
                                else:
                                    self_target_contig = 0   #for complete data, these will never be different
                            if outside_loci:
                                #Need to a correct spacer values if there are Ns that were masked
                                try:
                                    Ns_removed = affected_genomes[Acc_num]  #this will give a key error if the genome isn't Ns masked
                                    align_locus = correct_spacers_for_Ns(align_locus,Ns_removed,0,True)    
                                except KeyError:  #if not an affected genome
                                    pass
                        else: #(genome_type is WGS)
                            #Because the CRISPR search tool is not intelligent, need to convert position of spacer within entire file to within the contig of interest
                            #First need to determine the length of each contig (CRISPR find tool ignores newlines and first line in length
                            
                            contig_lengths = []
                            contigs_file = fastanames[Acc_num][0]
                            with open(contigs_file, 'r') as fileobj:
                                lines = fileobj.readlines()
                            summ = 0
                            contig_num = 0; self_target_contig = -1
                            for line in lines:
                                #because the order of the contigs is not determined (based on NCBI download order), need to find where it is in fasta file
                                try:
                                    subtitle = line.split("|")[1] #First try a split with '|', which would be present if a downloaded genome
                                except IndexError:
                                    subtitle = line
                                if subtitle.find(Acc_num_self_target) > -1 and self_target_contig < 0: 
                                    self_target_contig = contig_num  #Gives the contig number from the top
                                if contig_num == 0:
                                    summ = 0     #the current implementation is a bit ad hoc, essentially giving a slight pad to the locus, could always manually override.
                                else:
                                    summ += len(line.strip()) 
                                if line[0] == '>':
                                    contig_lengths.append(summ)  #Thus, the contig_length list will be a sum of the character list up to the end of each contig
                                    contig_num += 1                 
                
                            #Need to adjust locus range by subtracting all of the contigs that are farther up in the file
                            #Determine how many contigs need to be subtracted
                            if self_target_contig > 0:
                                alt_align_subtract = contig_lengths[self_target_contig]  #If in the opposite orientation, the last line will count toward 
                            else:
                                alt_align_subtract = 0
                            for locus in range(1,len(x)):
                                locus_range = [int(y) for y in x[locus][0].split("Range: ")[1].strip().split(" - ")]
                                lower_limit = locus_range[0] - pad_locus - alt_align_subtract
                                if lower_limit < 1:
                                    lower_limit = 1
                                upper_limit = locus_range[1] - alt_align_subtract + pad_locus
                                if lower_limit <= alt_alignment <= upper_limit:  #if falls within any locus
                                    outside_loci = False
                                    break
                            
                            if outside_loci:
                                #determine which contig it was in based on the lengths determined above & its correct length within its fragment
                                contig_num = 0
                                try:
                                    for length in contig_lengths:
                                        if align_locus < contig_lengths[contig_num+1]:
                                            try:
                                                Ns_removed = affected_genomes[Acc_num]  #this will give a key error if the genome isn't Ns masked
                                                align_locus = correct_spacers_for_Ns(align_locus,Ns_removed,contig_lengths[contig_num],True)    
                                            except KeyError:
                                                pass
                                            align_locus -= contig_lengths[contig_num]
                                            locus_Accs[Acc_num+Acc_num_self_target+str(align_locus)] = contig_Accs[Acc_num][contig_num]   #Used for replacing the WGS with the locus position later, complicated key to avoid clashes
                                            break
                                        elif contig_num == len(contig_lengths) - 2:  #At the second to last contig (but align_locus is larger), means contig is last position
                                            try:
                                                Ns_removed = affected_genomes[Acc_num]  #this will give a key error if the genome isn't Ns masked
                                                align_locus = correct_spacers_for_Ns(align_locus,Ns_removed,contig_lengths[contig_num+1],True)    
                                            except KeyError:
                                                pass
                                            align_locus -= contig_lengths[contig_num+1]
                                            locus_Accs[Acc_num+Acc_num_self_target+str(align_locus)] = contig_Accs[Acc_num][contig_num+1]
                                            break
                                        contig_num += 1
                                except: 
                                    locus_Accs[Acc_num+Acc_num_self_target+str(align_locus)] = contig_Accs[Acc_num][0] #will happen if only 1 contig, but marked as WGS
                                                         
                        if outside_loci:   #only keep alignments that don't match 
                            #Determine what the'PAM' sequence is after the non-locus alignment to report
                            PAM_seq_up,PAM_seq_down,species,Type_proteins,Type_repeat,locus_condition,proteins_found,self_target,consensus_repeat,repeat_mutations,spacer_seq,alt_alignment,align_locus,array_direction,target_sequence,false_positive = analyze_target_region(spacer_seq,fastanames,Acc_num_self_target,Acc_num,self_target_contig,alt_alignment,align_locus,direction,crispr,spacer,locus_Accs,provided_dir,genome_type,Cas_gene_distance,affected_genomes,alt_align_subtract,bin_path,protein_HMM_file,repeat_HMM_file,prefix,CDD,repeats)

                            if not false_positive:
                                blast_results_filtered_summary.append([Acc_num_self_target,  #Accession # of sequence with position of spacer target outside of array
                                                                        Acc_num,              #Accession # of sequence with position of spacer within array 
                                                                        species,              #Species pulled from GenBank file
                                                                        Type_proteins,        #Predicted CRISPR subtype based on locus protein contents
                                                                        Type_repeat,          #CRISPR subtype suggested by repeat sequence
                                                                        locus_condition,      #Description of locus relative to Makarova, 2015 Nat Rev Micro (Figure 2)
                                                                        proteins_found,       #Cas proteins found in the locus
                                                                        crispr,               #CRISPR number according to CRT results (for lookup in CRT results)
                                                                        spacer,               #spacer number according to CRT results (for lookup in CRT results)
                                                                        alt_alignment,        #Position of spacer target outside of array
                                                                        align_locus,          #Position of spacer within array 
                                                                        spacer_seq,           #Sequence of the self-targeting spacer 
                                                                        PAM_seq_up,           #Upstream 'PAM' sequence (upstream of target sequence)
                                                                        target_sequence,      #Sequence of the target of self-targeting spacer (to determine potential mismatches)
                                                                        PAM_seq_down,         #Downstream 'PAM' sequence (upstream of target sequence)
                                                                        consensus_repeat,     #Consensus repeat sequence 
                                                                        repeat_mutations,     #Mutations from the consensus repeat in the repeats before or after the spacer in the array
                                                                        array_direction,      #Direction of the array (forward or reverse)
                                                                        self_target,          #Genes that are targeted by the self-targeting spacer
                                                                        "N/A"])                #-placeholder- for PHASTER results (if later run)         
                                
        genome_number += 1 
    if blast_results_filtered_summary == []:
        print("No self-targeting spacers found. Exiting...")
        sys.exit()
    else:
        print("Done searching for self-targeting spacers. {0} self-targeting spacers found in total.".format(len(blast_results_filtered_summary)))

    return blast_results_filtered_summary,locus_Accs

def Export_results(in_island,not_in_island,unknown_islands,prefix,locus_Accs={},fastanames={}):

    #Export blast results that are in islands to a separate file 
    output_results(in_island,locus_Accs,fastanames,"{0}Spacers_inside_islands.txt".format(prefix))
                                            
    #Export blast results that aren't in islands to a separate file 
    output_results(not_in_island,locus_Accs,fastanames,"{0}Spacers_outside_islands.txt".format(prefix))
            
    if unknown_islands != []:
        #Export blast results that aren't analyzed with PHASTER into a last file
        output_results(unknown_islands,locus_Accs,fastanames,"{0}Spacers_no_PHASTER_analysis.txt".format(prefix))
    elif os.path.exists("{0}Spacers_no_PHASTER_analysis.txt".format(prefix)):   #deletes the temporary file
        os.remove("{0}Spacers_no_PHASTER_analysis.txt".format(prefix))
    
def output_results(results,replacement_dict,fastanames,filename):
    #Export results to a separate file 
    with open(filename,"w") as bfile:
        bfile.write("Assembly uID\tTarget Accession#\tLocus Accession#\tSpecies/Strain\tPredicted Type from Cas proteins\tPredicted Type from repeats\tLocus Completeness\tCas Genes Identified\tCRISPR #\tSpacer #\tSpacer Target Pos.\tSpacer Locus Pos.\tSpacer Sequence\tPAM Region (Upstream)\tTarget Sequence\tPAM Region (Downstream)\tConsensus Repeat\tRepeat Mutations\tArray Direction\tSelf-Target(s)\tPHASTER Island #\n") 
        if results != []:
            for line in results:
                if replacement_dict != {} and fastanames != {}:
                    x=''
                    if fastanames[line[2]][2] == 'WGS':
                        replace_Acc = True
                    else:
                        replace_Acc = False
                    column = 0
                    for y in line:
                        if column == 2 and replace_Acc:
                            x = x + replacement_dict[line[2]+line[1]+str(line[11])] + '\t'
                        else:
                            x = x + str(y) + "\t"
                        column += 1
                    bfile.write(x+"\n") 
                else:
                    bfile.write("\t".join([str(x) for x in line]) + '\n') 

def is_known_Cas_protein(product,types_list=[]):
    
    protein_name = ''; is_Cas = False
    for key,values in Cas_proteins.items():   #note, as additional Cas proteins are added, make sure Cas1, Cas2, etc. are at the bottom so Cas1 isn't found before Cas12
        if product.find(key) > -1:
            #Check to see if the protein type is annotated
            parts = [x.lower() for x in product.split(" ")]
            protein_name = key  #return the found hit 
            for part in parts:
                if "type" in part and part != parts[-1]:   #ignore things that end in type
                    type_expected = "Type " + parts[parts.index(part) + 1].upper()  #find type and look next to it for the designation
                    #If a type pops up, but the letter is not there, add all possibilities
                    for value in values:
                        if type_expected == value.split("-")[0]:  
                            types_list.append(value)  #Adds weight that the proper type will be identified
                    break
            types_list += values   #the correct Type will have the most entries in this list
            is_Cas = True
            break 
    return is_Cas,protein_name,types_list    #Returns the CRISPR type if detected and whether the locus appears complete

def grab_feature(feature):
    
    try:
        feature_num = feature.qualifiers["protein_id"][0]
        target_protein = feature.qualifiers["product"][0] 
    except KeyError or AttributeError:  #No protein_id associated, such as a pseudo-gene, or not a protein
        try:
            feature_num = "locus tag: " + feature.qualifiers["locus_tag"][0] 
            target_protein = feature.type 
        except KeyError or AttributeError:
            feature_num = feature.type
            target_protein = str(feature.location)
        
    return feature_num, target_protein

def HMM_Cas_protein_search(check_list,check_aa,prefix,bin_path,protein_HMM_file):
    
    #First convert the protein names and sequences into a fasta formatted file:
    with open("{0}temp/HMM_Cas_search.fa".format(prefix), 'w') as file1:
        index = 0
        for protein in check_list:
            file1.write(">{0}\n{1}\n".format(protein,check_aa[index]))
            index += 1
    hmm_cmd = "{0}hmmscan -E 1e-6 --tblout {1}temp/HMM_results.txt {2} {1}temp/HMM_Cas_search.fa".format(bin_path,prefix,protein_HMM_file)
    handle = subprocess.Popen(hmm_cmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    output, error = handle.communicate()
    if error != '':
        print("Error in HMMScan for proteins\n", error)
        sys.exit()        
    #Parse the output to find the best alignments to Cas proteins
    with open("{0}temp/HMM_results.txt".format(prefix),"r") as file1:
        lines = file1.readlines()
    short_names = []
    for line in lines:
        if line[0] != "#":   #All lines that aren't data are marked with a hash sign
            try:
                short_names.append(line.split()[2] + "\t" + line.split()[0])
            except IndexError:
                pass
    
    return short_names

def CDD_homology_search(check_list):
    
    ##Need to POST data to CDD     https://www.ncbi.nlm.nih.gov/Structure/bwrpsb/bwrpsb.cgi
    #cdsid - search string associated with the requested search
    #db - specify name of database
    #smode = search mode (auto)
    #queries - Acc numbers
    #tdata - data type (target data) desired in the output. Allowable values are: "hits" (domain hits), "aligns" (alignment details), or "feats" (features).
    
    session = requests.session()
    url = "https://www.ncbi.nlm.nih.gov/Structure/bwrpsb/bwrpsb.cgi"  #batch input
    new_search = {"db":"cdd",     #Define the dictionary that will POST the details of search for the unknown proteins
                "smode":"auto",
                "queries":check_list,  
                "dmode":"full",
                "tdata":"hits"}
    
    #POST the results first 
    tries = 0
    while tries <= 3:
        tries += 1
        try:
            r = session.post(url, new_search,timeout=40)
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
            time.sleep(5) #wait an additional 5 seconds before trying again
            
    try_count = 0
    while try_count <= 30:
        try_count += 1
        short_names = []
        
        if try_count > 10:
            print("Trying to overcome issues with CDD speed/connectivity...")
        
        for line in r.text.split("\n"):
            if line.find("cdsid") > -1:
                cdsid = line.split("cdsid")[1].strip()  #Extract the cdsid number
            if line.find("status") > -1:
                statuscode = line.split("\t")[1].strip()   #0 - success, 2 - no input, 3 - running, 1,4,5 are errors
                break
        else:
            statuscode = -1    #this status code that indicates still waiting for a response
        
        if statuscode in ('1','4','5'):
            print("Error in protein homology search. Retrying...")    
        elif statuscode == '2':
            #nothing to check, should be caught above
            break
        elif statuscode == '3':
            time.sleep(3) 
            tries = 0
            while tries <= 3:
                tries += 1
                try:
                    r = session.get(url+"?cdsid={0}".format(cdsid),timeout=30)   #Retry after 5 seconds with GET
                except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                    time.sleep(3) #wait an additional 3 seconds before trying again
        elif statuscode == '0':
            #Parse out the data
            for line in r.text.split("\n"):
                data = line.split("\t")                        
                if data[0].split(" - ")[0][:2] == "Q#":  #look for results by finding early tags
                    short_names.append(data[0]+'\t'+data[8])  #Couples the Accession number of the found protein with the short name for its CD search hit
            break        
    
    return short_names

def label_self_target(target_protein,feature_num):
    
    if target_protein == 'hypothetical protein':
        short_names = CDD_homology_search([feature_num])
        labels = [x.split('\t')[1] for x in short_names] #removes the leading accession # used to track pseudogenes for the CRISPR locus
        if len(labels) > 3:
            target_protein = ", ".join(labels[:3]) + " (CDD homology search)"
        elif len(labels) > 0:
            target_protein = ", ".join(labels)  + " (CDD homology search)"
   
    return target_protein

def self_target_search(provided_dir,input_list_file,search,num_limit,E_value_limit,CRT_params,pad_locus,complete_only,skip_PHASTER,percent_reject,default_limit,redownload,current_dir,bin_path,Cas_gene_distance,protein_HMM_file,repeat_HMM_file,prefix,CDD=False,ask=False):

    if not os.path.exists('{0}temp'.format(prefix)):
            os.mkdir('{0}temp'.format(prefix))  
            
    if num_limit == 0:
        num_limit = default_limit        
    
    #Creates a report of the search parameters
    print_search_criteria(search,num_limit,default_limit,provided_dir,E_value_limit,pad_locus,CRT_params,percent_reject,skip_PHASTER)
    
    #Fetch the fasta files in the provided directory
    if provided_dir != '':
        fastanames,provided_complete_counter,provided_WGS_counter = load_provided(provided_dir,num_limit,complete_only)
   
    #Search NCBI using the given term, finding all relevant genomes
    if search != '':
        found_complete,found_WGS,total,complete_IDs,WGS_IDs,wgs_master_GIs,num_genomes = search_NCBI_genomes(search,num_limit,complete_only)
        #Download the appropriate genomes
        if provided_dir == '':
            fastanames = {}
            fastanames,Acc_convert_to_GI = download_genomes(total,num_limit,num_genomes,found_complete,search,redownload,provided_dir,current_dir,found_WGS,complete_IDs,WGS_IDs,wgs_master_GIs,fastanames,ask,prefix)

    #Assembly list is used to find genomes here
    if search == '' and input_list_file != '':
        fastanames, Acc_convert_to_GI = prep_assemblies_list(input_list_file, num_limit, complete_only,redownload,current_dir,prefix)

    #Search each genome for CRIPSR repeat-spacers
    CRISPR_results, affected_genomes = spacer_scanner(fastanames,bin_path,CRT_params,current_dir,prefix)
    
    #BLAST each spacer sequence against the genome
    spacer_data,num_loci = get_loci(CRISPR_results,fastanames,affected_genomes)

    #Check to see which of the spacers appears in the genome outside of any indentified CRIPSR loci
    blast_results = spacer_BLAST(spacer_data,fastanames,num_loci,percent_reject,current_dir,bin_path,E_value_limit)
    
    #Look at spacers that are outside of the annotated loci and gather information about the originating locus and its target
    blast_results_filtered_summary, locus_Accs = self_target_analysis(blast_results,spacer_data,pad_locus,fastanames,provided_dir,Cas_gene_distance,affected_genomes,bin_path,protein_HMM_file,repeat_HMM_file,prefix,CDD,CRT_params[0])

    #Determine the Assembly uIDs and append to the 5' end
    #first, get a list of the nucleotide accession numbers:
    Nuc_Accs = [x[0] for x in blast_results_filtered_summary]
    final_data = []; i= 0
    if provided_dir == '':
        print("Looking up Assembly uIDs...")
        Assem_uIDs = nucleotide_acc_to_assembly_acc.main(Nuc_Accs)
        for row in blast_results_filtered_summary:
            final_data.append([Assem_uIDs[i]] + row)
            i += 1
    else:
        print("Files were provided, looking for genbank files in 'GenBank_files/'...")
        for row in blast_results_filtered_summary:
            final_data.append(['undetermined'] + row)
            i += 1
    
    #Export all of the results to a text file (to have preliminary results while waiting for PHASTER)
    output_results(final_data,locus_Accs,fastanames,"{0}Spacers_no_PHASTER_analysis.txt".format(prefix))
    
    if not skip_PHASTER:
        in_island,not_in_island,unknown_islands,protein_list = PHASTER_analysis(final_data,current_dir)
        Export_results(in_island,not_in_island,unknown_islands,prefix,locus_Accs,fastanames)
        print("PHASTER analysis complete.")
    else:
        protein_list = []
        print("Skipping PHASTER analysis")

    return protein_list     
                                
def PHASTER_analysis(final_data,current_dir):

    in_island = []
    not_in_island = []
    unknown_islands = []       
    protein_list = []
    #Now will search to see if hits are in phage islands using PHASTER
    #and store all the unassigned proteins per hit
    print("Running PHASTER analysis...")
    if not os.path.exists("PHASTER_analysis"):
        os.mkdir("PHASTER_analysis")
    for potential_hit in final_data:
        skip_entry = True
        #First determine if the analysis has been done before
        Acc_to_search = potential_hit[1]  #If WGS, use the contig itself to search    
        PHASTER_file = current_dir+"PHASTER_analysis/" + Acc_to_search.split(".")[0] + ".txt"
        if os.path.isfile(PHASTER_file):
            #If it has, just load the results
            with open(PHASTER_file, 'r') as input_file:
                lines = [x.strip() for x in input_file.readlines()]
            if lines != []:
                skip_entry = False
            else:
                os.remove(PHASTER_file)
        if skip_entry:   #if a PHASTER file wasn't found, do the search
            lines,skip_entry = query_PHASTER(Acc_to_search,PHASTER_file,current_dir,post=False)  #first try a simple lookup with the the Acc number, post the sequence if it fails
            if skip_entry == True:   #If a simple Acc lookup didn't work, try POSTing genbank files
                lines,skip_entry = query_PHASTER(Acc_to_search,PHASTER_file,current_dir,post=True) 
        if not skip_entry:
            record = False
            region = 0
            found_island = False
            for line in lines:
                if record == True:
                    region += 1  #note what region the spacer was found in
                    string = line.strip()
                    results = list(filter(None, string.split(" ")))
                    if results != []:
                        island_start = int(results[4].split("-")[0])
                        island_end = int(results[4].split("-")[1])
                        spacer_pos = potential_hit[10]
                        temp = potential_hit
                        if island_start <= spacer_pos <= island_end:  #check to see if in an island
                            found_island = True
                            temp = potential_hit[:-1] + [region]  #replace 'N/A' in PHASTER island with the island number
                            break
                    elif region == 1 and results == []:
                        temp = potential_hit[:-1] + ["none identified"]   #replace 'N/A' in PHASTER island if no islands are found   
                    elif region > 1 and not found_island:  
                        temp = potential_hit[:-1] + ["outside island(s)"]   #replace 'N/A' in PHASTER island if spacer found outside all the islands   
                elif line.strip()[-4:] == "----":
                    record = True
            if found_island:   #put into categories based on whether it was in an island
                in_island.append(temp)
            else:
                not_in_island.append(temp)
        else: 
            print("Skipping analysis of {0}".format(Acc_to_search))
            unknown_islands.append(potential_hit)
    print("PHASTER analysis finished.")
    
    return in_island,not_in_island,unknown_islands,protein_list

def query_PHASTER(Acc_to_search,PHASTER_file,current_dir,post=False):
    
    #Use post to switch to uploading sequence that doesn't have an Acc number, not written into code yet
    lines = []
    Acc_to_print = Acc_to_search
    url = "http://phaster.ca/phaster_api"
    json_err = 0
    while True:
        try:
            if post:
                #Get the GenBank file and post that
                genfile_name = current_dir+"GenBank_files/"+Acc_to_search.split(".")[0] + ".gb"
                if not os.path.exists(genfile_name):
                    print("GenBank file for {0} needed and missing, downloading...".format(Acc_to_search))
                    record = download_genbank(Acc_to_search)
                else:
                    record = SeqIO.read(genfile_name, 'genbank')
                seq_len = len(record.seq)
                if seq_len >= 2000:    #Required for PHASTER
                    with open(genfile_name, 'rb') as payload:
                        headers = {'content-type': 'application/x-www-form-urlencoded'}
                        r = requests.post(url,data=payload, verify=False, headers=headers)
                else:
                    print("Contig {0} is only {1} nts, skipping...".format(Acc_to_search,seq_len))
                    skip_entry = True
                    lines = []
                    time.sleep(1)
                    return lines,skip_entry    
            else:
                r = requests.get(url+"?acc={0}".format(Acc_to_search), timeout=20)  #do a PHASTER search in the potential hits genome
            try:
                json_err += 1
                r2 = r.json()
                json_err = 0
            except ValueError as err:  #catches JSON objects that can't be decoded
                if json_err == 3:  #Give it three chances to decode it
                    print(err)
                    print("JSON decode error. Skipping {0}...".format(Acc_to_print))
                    skip_entry = True
                    lines = []
                    return lines,skip_entry 
                else:
                    time.sleep(5)  #wait 5 seconds before retrying
                    continue
 
            if post:
                Acc_to_search = str(r2[u'job_id'])   #switch Acc_to_search temporarily to the idea to search
                post = False  #Once posted, can switch to GET for job status requests
            try:
                r3 = r2[u'summary']
                lines = str(r3).split("\n")
                skip_entry = False
                break
            except KeyError:
                try:
                    msg = str(r2[u'error']).strip()
                    print(msg + "\nError with PHASTER looking for '{0}'".format(Acc_to_print))
                    skip_entry = True
                    lines = []
                    time.sleep(1)
                    return lines,skip_entry
                except KeyError:
                    time.sleep(30)           #wait 30s before retrying 
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            time.sleep(3)  #wait 3 seconds before retrying
            pass    
        except requests.exceptions.ChunkedEncodingError:
            time.sleep(3)  #wait 3 seconds before retrying
            pass  
        
    #Write the PHASTER results to a file
    with open(PHASTER_file, "w") as jot_notes:
        for line in lines:
            jot_notes.write(line + "\n")                     

    return lines,skip_entry

def import_data(input_file):
    #read files into data structure, should be in output format from code above
    with open(input_file, 'r') as fileread:
            lines = fileread.readlines()
    imported_data = []
    for line in lines:
        if line.find('Target Accession#') == -1 and line != []:  #skip header lines
            word_num = 0
            converted_line = []
            for word in line.strip().split('\t'):
                if word_num in (8,9,10,11):    #These are the positions in the data (0 indexed) that should be integers
                    converted_line.append(int(word))
                else:
                    converted_line.append(word)
                word_num += 1
            imported_data.append(converted_line)
              
    return imported_data

def check_dependencies():
    #Will quickly check for:
    dependencies = ['clustalo','blastn','nhmmscan','hmmscan']
    
    missing_dependencies = []
    for dependent in dependencies:
        if not os.path.isfile("{0}/{1}".format(bin_path,dependent)):
            missing_dependencies.append(dependent)
    if missing_dependencies != []:
        print("Missing the following required binary(ies) in bin/ (must be named as listed): {0}".format(", ".join(missing_dependencies)))
        sys.exit()

def main(argv=None):
    
    current_dir = os.getcwd()+'/'
    params = Params()     
    try:
        if argv is None:
            argv = sys.argv
            args,num_limit,E_value_limit,provided_dir,search,CRT_params,pad_locus,complete_only,skip_PHASTER,percent_reject,default_limit,redownload,rerun_PHASTER,spacer_rerun_file,skip_alignment,ask,input_list_file,rerun_loci,Cas_gene_distance,HMM_dir,prefix,CDD,protein_HMM_file,repeat_HMM_file,group = params.parse_options(argv)
        
        #Run a check to make sure binaries are present
        check_dependencies()
        
        if Cas_gene_distance == 0:
            global all_contigs_checked
            global Cas_gene_analysis_dict
            Cas_gene_analysis_dict = {}
            all_contigs_checked = []
        
        if not os.path.exists('{0}temp'.format(prefix)) and not rerun_PHASTER:
            os.mkdir('{0}temp'.format(prefix))

        if rerun_PHASTER:    #Used to rerun the PHASTER analysis
            imported_data = import_data(spacer_rerun_file)
            in_island,not_in_island,unknown_islands,protein_list = PHASTER_analysis(imported_data,current_dir)
            Export_results(in_island,not_in_island,unknown_islands,prefix)
        elif rerun_loci:     #Used to rerun the loci annotating code near the spacers found
            imported_data = import_data(spacer_rerun_file)
            #First recheck the proteins near the spacer
            re_analyzed_data = locus_re_annotator(imported_data,Cas_gene_distance,protein_HMM_file,repeat_HMM_file,prefix,CDD)
            #Then check the repeat again for direction, Type, etc.
            output_results(re_analyzed_data,{},{},"{0}{1}_re-analyzed.txt".format(prefix,spacer_rerun_file.split(".")[0]))   #Quickly re-generate the re-analyzed data.
        elif group:
            orig_dir = current_dir
            groups_to_search = import_list(input_list_file)
            for group_to_search in groups_to_search:
                groups_remaining = groups_to_search[groups_to_search.index(group_to_search):]
                rescue_list(groups_remaining)
                dir_name = group_to_search.replace(" ", "_")
                if not os.path.exists(dir_name):
                    os.mkdir(dir_name)
                try:
                    os.chdir(dir_name)
                    print("\nCurrently in {0} directory.".format(dir_name))
                except:
                    print("Cannot get into {0}. Exiting...".format(dir_name))
                    sys.exit()
                provided_dir = ''
                print("Searching '{0}'...\n{1}\n".format(group_to_search, str(datetime.now())))

                # Identify genomes that contain self-targeting spacers
                current_dir = orig_dir + dir_name + "/"
                try:
                    protein_list = self_target_search(provided_dir,input_list_file,group_to_search, num_limit, E_value_limit, CRT_params, pad_locus,complete_only,skip_PHASTER,percent_reject,default_limit,redownload,current_dir,bin_path,Cas_gene_distance,protein_HMM_file,repeat_HMM_file,prefix,CDD,False)
                    protein_list = []  # Currently not used, clear memory
                except SystemExit:
                    pass  # Presumedly, this is raised when further analysis in a group isn't necessary
                os.chdir(orig_dir)
        else:
            #Identify genomes that contain self-targeting spacers
            protein_list = self_target_search(provided_dir,input_list_file,search,num_limit,E_value_limit,CRT_params,pad_locus,complete_only,skip_PHASTER,percent_reject,default_limit,redownload,current_dir,bin_path,Cas_gene_distance,protein_HMM_file,repeat_HMM_file,prefix,CDD,ask)
            #protein_list is a placeholder for potential future development
                                  
    except Usage as err:
        print(err)
        return 2

if __name__ == "__main__":
    sys.exit(main())
