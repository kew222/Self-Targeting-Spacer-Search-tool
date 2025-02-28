# Self-Targeting Spacer Searcher (STSS)

## About STSS

STSS was written to search prokaryotic genomes for CRISPR arrays and determine if any of the spacers in the array target the organism's own genome. Each self-targeting spacer (STS) that is found is checked for mutations in the repeat, target sequence, or PAM as well as for missing Cas genes. What gene(s) is/are being targeted is also determined and whether the targeted positions occur in a prophage are checked with PHASTER (Arndt, D., Grant, J., Marcu, A., Sajed, T., Pon, A., Liang, Y., Wishart, D.S. (2016) PHASTER: a better, faster version of the PHAST phage search tool. Nucleic Acids Res., 2016 May 3.).

### Installation

#### Requirements:

- Python 3 (previous versions are written for Python 2)
- Biopython
- requests (Python package)
- blastn (available from NCBI)
- Clustal Omega
- HMMER 3
- Internet connection

#### Instructions

First, clone the STSS repository with:

`git clone https:github.com/kew222/Self-Targeting-Spacer-Search-tool.git`

Install blastn from NCBI (ftp:ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/).

For recognition by STSS, all of the required binaries need to be visible in the bin/ directory in the repository. We recommend installing or placing all binaries in /usr/local/bin/ and creating a link to the STSS bin/ directory with (as an example):

`ln -s /usr/local/bin/blastn STSS/bin/blastn`

If not storing the binaries at /usr/local/bin is undesired (such as in a server environment), simply replace with the location of the binaries. Alternatively, the binaries can be placed directly in the bin/ directory in STSS.

Install Clustal Omega from (http:www.clustal.org/omega/#Download). Again, precompiled binaries are available for quick use, although compiling from source is also an option. After choosing the appropriate operating system, link to bin/ with (ex.):

`ln -s /usr/local/bin/clustalo STSS/bin/clustalo`

The last required non-Python binary is HMMER3 (http:hmmer.org/download.html) for which binaries are again available. Following the same method as before, move the binaries (or compile) to a centralized location and link (at minimum) nhmmscan and hmmscan to bin/, for example:

`ln -s /usr/local/bin/*hmm* STSS/bin/`

With all of the binaries in place for STSS, all that remains to set up the Python packages to run. This can be done by simplying running:

`python setup.py install` 

from the STSS directory. This will check for Biopython and the requests package and install them if they are missing. At this point everything should be installed.

Before running STSS, however, you will need to edit user_email.py (using any standard text editor) to input your email address, which is needed for running the NCBI tools. This will only need to be done once. STSS has no email collecting code, etc. so we will never see your email address. 


### Workflow

In order to find STSs, STSS goes through the following steps (described in more detail in: _Systematic discovery of natural CRISPR-Cas12 inhibitors_):

1. Gathers genomes (either provided or by searching NCBI)
2. Uses the CRISPR Recogition Tool (CRT; Bland, C. et al. CRISPR Recognition Tool (CRT): a tool for automatic detection of clustered regularly interspaced palindromic repeats. BMC Bioinformatics 8, 209–8 (2007)) to identify CRISPR arrays
   - Because CRT cannot handle genomes with long degenerate stretches, these are effectively masked before CRT analysis
   - Also, CRT has a propensity to put repeats in the spacer sequences. Arrays are double-checked for similarity at the beginning and ends of the spacers to find incorrectly called repeat sequences and fixes them heurestically.
3. Performs a BLAST search on the genome with each spacer found (must be outside bounds of found arrays)
4. The array containing the STS is checked for Cas gene content using HMMER3 or the Conserved Domain Database (CDD; NCBI)
5. The array consensus repeat is determined and the repeats on either side of the STS are checked
6. The direction of the array is determined with either the Cas genes and/or the repeat sequence
7. The targeted gene in the genome is determined, possibly using the CDD to find domains if not annotated
8. Any mutations between the target and the guide RNA are determined as well as the upstream/downstream neighboring sequences
9. Last, the targeted contig is checked for prophages with PHASTER to determine if the STS is in a prophage
10. (Optional) Use Spacer_data_compiler.py to combine all the STSS output files into one file.
11. (Optional) Use anti-CRISPR_annotate.py to add an additional column to the STSS output files to search for known anti-CRISPR proteins in the target contig. The help file is fairly self-explanatory.


### Usage

#### Running STSS

STSS can accept a couple different formats for searching genomes for self targeting spacers. In the simplist case, the user might want to search for STSs in all of one organism say _E. coli_. To search all _E. coli_ genomes:

`python STSS.py --search "Escherichia coli"`

Note that the quotes will be required for multi-word terms. Also, the search term is used to search the [organism] tag on NCBI (Genomes). That is, the example search string on NCBI would be: "Escherichia coli[organism]" Thus, specific strains cannot be searched this way, only down to the species level.

Alternatively, the user could determine the genomes he/she wants to search and download them (the input is required to be fasta formatted!). In that case, STSS can be given a directory containing genomes to search in:

`python STSS.py --dir downloaded_genomes/`

This method is also useful if the genomes to be searched are not on NCBI. However, some of the capabilities of STSS will be limited if there isn't an NCBI Accession number to use or it can't determine it from the fasta file. This can be somewhat overcome if there is a GenBank formatted file (.gb) provided with the same name for STSS to find. That Genbank file is going to be searched for in a directory named 'GenBank_files/' - if it's not there further analysis will fail (this directory is automatically made using the --search option).

Last, STSS can also accept a list of assemblies as NCBI uIDs to find and download the genomes of interest (assuming they are listed in a file named assemblies.txt):

`python STSS.py --list assemblies.txt`

The results from any running method will be same. There will generally be two tab-delimited files with the same formats, one containing the STSs that were found to be in prophages and the other that were not. If the PHASTER analysis was skipped (see options below), only one file will be output. Last, before PHASTER analysis, all of the results are dumped into one file, that is updated to only include hits that are incapable of running on PHASTER after all of the PHASTER runs are completed.

#### Test Case

To confirm that the code is working correctly, we recommend either running --search with "Moraxella bovoculi" or --list using assemblies.txt (contains assembly uID 330201 - M. bovoculi strain 33362). There is one self-targeting spacer in that genome, and the output should match the results found in Test_Case_results.txt.

#### Options

Option |  Description
-------| ------------
-h, --help               |       Opens help message  
-v, --version              |     Displays version number  
--dir <directory>            |   Use directory of genomes (fasta-formatted) instead of searching NCBI  
--search <"NCBI search term"> |  Use NCBI nucleotide database to find genomes with a search string   
-g, --groups <groups_file>   |   Provide a list of search terms in an input file to loop over
--list <Assembly_uID_list_file> |    Search genomes based on a given list of assemblies (incompatible with search). Requires that the assemblies are provided as a list of uIDs, NOT accessions.   
-o, --prefix <string>        |   Prefix for filenames in output (ex. prefix of 'bagel' gives: bagel_Spacers...islands.txt)  
-f, --force-redownload      |    Forces redownloading of genomes that were already downloaded  

Use -f if using search and want to force the redownload of any genomes that already exist in the downloaded_genomes directory.  

Option |  Description
-------| ------------
-n, --no-ask            |        Force downloading of genomes regardless of number found (default: ask) 

By default, STSS will ask the user if he/she wants to continue with the download if there are large number of files returned. There is a delay while searching NCBI, so turning the option off will prevent the need to wait to confirm the download if hard drive space is not an issue. If the --groups option is used, this is automatically changed to --no-ask so the user doesn't have to monitor the multiple searches.

Option |  Description
-------| ------------
-l, --limit <N>         |        Limit Entrez search to the first N results found (default: 200000) 

Lowering this value is unnessecary for small searches, but may need to be raised for large scale searches.  

Option |  Description
-------| ------------
--CDD                    |       Use the Conserved Domain Database to identify Cas proteins (default is to use HMMs) 

By default, HMMs are used to try to identify Cas proteins near arrays or in the genome (see option -d). However, the CDD can also be used. The main difference other than the use of HMMs vs. PSWMs, is which database was updated most recently. CDD can be slow to update, but depending on how often the provided HMMs are updated, it may be more useful to use CDD in the future. Using HMMER locally is much faster than the CDD due to the need to use webservers for the CDD. 

Option |  Description
-------| ------------
--Cas-HMMs <filename>     |       Use the provided HMMs for the Cas proteins instead of the provided set 
--repeat-HMMs <filename>   |     Use the provided HMMs for the repeat prediction instead of the provided set 

Prebuilt HMMs are available for both the Cas proteins and repeat sequences (stored in the HMMs/ directory). However, the user can create their own HMMs for use and supply them with these options.


Option |  Description
-------| ------------
--complete-only         |        Only return complete genomes from NCBI 
--rerun-loci <filename>    |     Rerun the locus annotater to recheck the nearby locus for Type and completeness from provided spacer search results file 

When --rerun-loci is used, a results file from a previous run must be given. This option will rerun all of the data collection steps (steps 4-9 in Workflow above) using the previously found STSs. Note that the fields generated from the Cas protein locus analysis will always be overwritten, so manual edits will be overwritten. However, this is not the case for the repeats fields. For the repeats the orientation will be double-checked with the repeat HMMs and all of these fields will be reversed if the array is found to be noted in the wrong direction; the contents of the fields will not be edited otherwise.


Option |  Description
-------| ------------
-E, --E-value  <N>        |      Upper limit of E-value to accept BLAST results as protein family (default: 1e-4) 

Note that this E-value is a blanket value for all relevant tools. 

Option |  Description
-------| ------------
--percent-reject <N>       |     Percentage (of 100%) to use a cutoff from the average spacer length to reject validity of a proposed locus (default 25%). Lower values are more strigent. 

Adjust the percent-reject value will tune how much deviation is allowed from the average spacer length to try to determine array false positives. A lower percent will be more stringent and reject more arrays as false positives. This was an ad-hoc addition after we observed that most of the arrays identified by CRT that were not actually CRISPR arrays typically had a spacers with a variety of lengths, while correct arrays don't vary as much. Note, however, that Class 1 arrays do have some natural variability in length, so being too stringent can reject good arrays. 

Option |  Description
-------| ------------
-s, --spacers <N>       |        Number of spacers needed to declare a CRISPR locus (default: 3)  
--min-repeat-length <N> |         Minimum repeat length for the CRISPR array search (default: 18)
--max-repeat-length <N> |         Maximum repeat length for the CRISPR array search (default: 45)
--min-spacer-length <N> |         Minimum spacer length for the CRISPR array search (default: 18)
--max-spacer-length <N> |         Maximum spacer length for the CRISPR array search (default: 45)
--pad-locus <N>         |        Include a buffer around a potential locus to prevent missed repeats from appearing as hits (default: 100) 

The first five options are for changing the parameters of the CRT search. The pad-locus value is an ad-hoc correction to prevent spacers near the edges of arrays from being picked up as false positives. The main reason for including this factor is due to how CRT determines position, which ignores separations between contigs. 

Option |  Description
-------| ------------
-d, --Cas-gene-distance <N>  |   Window around an array to search for Cas proteins to determine CRISPR subtype (default: 20000 - input 0 to search whole genome)  

When determining the array Type, the genes up- and downstream of identified arrays are checked to see if and what Cas genes they contain using HMMs or PSWMs. By default, STSS searches 20k bases away from the start of an array. However, there are cases where a lot of Cas genes are present for an array that could cause some genes to be missed outside this range. In these cases, it may be advisable to increase the search distance. As a second option, all of the contigs of a genome (i.e., the whole genome) can be searched if '0' is input. Be aware, however, that STSS will still try to guess a CRISPR type based on the Cas genes identified by default, which is meaningless if multiple CRISPR systems exist in the genome. 

Option |  Description
-------| ------------
--skip-PHASTER                |  Skip PHASTER analysis 
-p, --rerun-PHASTER <filename> | Rerun PHASTER to recheck islands from provided Spacer search results file  

Only reruns the PHASTER analysis and does not recheck anything else in the results. Requires a results file from a previous run in the STSS output format.


#### Other notes:

- CRT is fairly greedy and will propose some arrays that aren't real. While there are number of corrections/detections built into STSS to try to eliminate as many as possible, a few still get through sometimes. We recommend doing a manually look over the output and remove any suspect sequences. 
- The repeat HMMs used for determining type and direction of the arrays are based on the REPEATS data and groupings (Sita J. Lange, Omer S. Alkhnbashi, Dominic Rose, Sebastian Will and Rolf Backofen. CRISPRmap: an automated classification of repeat conservation in prokaryotic adaptive immune systems. Nucleic Acids Research, 2013, 41(17), 8034-8044.), with additional repeat groupings added and some of the original families' orientations corrected. There are still many repeats that will not be recognized by these HMMs due to the wide diversity of repeat sequences.
- The main use of the --rerun-loci option is intended to provide a quick way to recheck found self-targeting spacers against updated or alternative HMMs. 
- Self-targeting spacers found in contigs that do not have GenBank annotations will not have proteins found in them, as STSS is currently not set up to handle finding ORFs and checking them for proteins. This is a feature we are considering adding in a future release.
- There is currently no way for STSS to directly call type II-C CRISPR systems because there are no distinguishing proteins relative to II-A and II-B (e.g. Csn2 or Cas4). Because of this, the user will need to manually determine the subtype, which will be marked as an unknown type II in the results.
- There are also some other scripts in the repository for automatically scanning NCBI for updates as well as a few scripts for checking the STSS results for the presence of anti-CRISPR proteins (i.e. anti-CRISPR_annotate.py). These scripts are fairly self-explanatory and, for the anti-CRISPR annotator, come with a list of known Acrs that can be modified by the user. The scripts are a bit slow however.







