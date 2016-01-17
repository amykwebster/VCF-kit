#! /usr/bin/env python
"""
usage:
  tb vcf2sql (bigquery|postgres|mysql|sqlite) <vcf>

options:
  -h --help                   Show this screen.
  --version                   Show version.

"""
from docopt import docopt
from utils.vcf import *
from subprocess import Popen, PIPE
import sys
import os
import re
import itertools
import gzip
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)



load_bigquery = r"""
#!/usr/bin/bash
# Load Bigquery

# [ ] Add instructions on getting set up...

gsutil cp {tsv_out} gs://andersen/annotation/{tsv_out}

# Load on bigquery
bq load --field_delimiter "\t" andersen-lab:Variation.{vcf_safe} gs://andersen/{tsv_out} {bigquery_schema}

"""

def bcftools_query(var_collection):
    query = []
    format_var_start = False
    for var, var_num, var_type, decription, group in var_collection:
        if group == "STANDARD":
            var = "%" + var
        elif group == "INFO":
            var = "%INFO/" + var
        elif group == "FORMAT":
            if format_var_start is False:
                var = "-->[%" + var
                format_var_start = True
            else:
                var = "%" + var
        query.append(var)
    query_in = r"\t".join(query) + r"\t%SAMPLE<--]\n"
    comm =  Popen(["bcftools", "query", "-f", query_in , v.filename], stdout=PIPE, stderr=PIPE)
    for line in comm.stdout:
        line = line.strip().split("-->")
        for sample_line in line[1].split("<--"):
            set_line = line[0] + sample_line
            set_line = zip(var_collection, set_line.split("\t"))
            out_line = []
            if sample_line:
                for q, o in set_line:
                    if q[2] == "Flag" and o == ".":
                        out_line.append("0")
                    elif q[2] == "Flag" and o != ".":
                        out_line.append("1")
                    elif o == ".":
                        out_line.append("")
                    else:
                        out_line.append(o)
                yield "\t".join(out_line)
      

def bigquery_schema(var_collection):
    var_set = []
    for var, var_num, var_type, decription, group in var_collection:
        try:
            var_num = int(var_num)
        except:
            var_num = 1
            var_type = "STRING"
        if var_type == "Flag":
            var_type = "BOOLEAN"
        if var_num > 1:
            var_type = "STRING"
        if group == "FORMAT":
            var = "F_" + var
        var_set.append([var, var_type.upper()])
    return var_set

def alert_script(script_name, script):
    """
        Prints script to user, notifies of location
    """
    with open(script_name, "w") as f:
        f.write(script)
    with indent(4):
        puts(colored.blue('\nA script named ' + script_name + ' has been created. Run it to load the VCF when the the tsv is output.\n'))
    puts(colored.blue("<----- Script Contents ----->" + script + "<--- End Script Contents --->"))

# Standard Columns
standard = (("CHROM", 1, "String", "Chromosome/Contig", "STANDARD"),
            ("POS", 1, "Integer", "Chromosome/Contig Position", "STANDARD"),
            ("ID", 1, "String", "Variant ID", "STANDARD"),
            ("REF", 1, "String", "Reference Allele", "STANDARD"),
            ("ALT", 1, "String", "Alternative Alleles (list)", "STANDARD"),
            ("QUAL", 1, "Float", "Variant Quality", "STANDARD"),
            ("FILTER", 1, "String", "Variant Filters", "STANDARD"))


# Info
r_info = re.compile(r'''\#\#INFO=<
  ID=(?P<id>[^,]+),
  Number=(?P<number>-?\d+|\.|[AG]),
  Type=(?P<type>Integer|Float|Flag|Character|String),
  Description="(?P<desc>[^"]*)".*
  >''', re.VERBOSE)

# Format
r_format = re.compile(r'''\#\#FORMAT=<
  ID=(?P<id>.+),
  Number=(?P<number>-?\d+|\.|[AG]),
  Type=(?P<type>.+),
  Description="(?P<desc>.*)".*
  >''', re.VERBOSE)


debug = None
if len(sys.argv) == 1:
    debug = ['vcf2sql', "test.vcf.gz"]

if __name__ == '__main__':
    args = docopt(__doc__,
                  argv=debug,
                  options_first=False)

    module_path = os.path.split(os.path.realpath(__file__))[0]
    v = vcf(args["<vcf>"])
    vcf_safe = v.filename.replace(".","_")
    tsv_out = v.filename.replace("vcf","tsv").replace("bcf","tsv").replace(".gz","") + ".gz"

    info_cols = [list(x) + ["INFO"] for x in r_info.findall(v.raw_header)]
    format_cols = [list(x) + ["FORMAT"] for x in r_format.findall(v.raw_header)]

    if args["bigquery"]:
        # Combine variable sets
        var_set = list(itertools.chain(standard, info_cols, format_cols)) + [("SAMPLE", 1, "STRING", "Sample Name", "STANDARD")]
        # Generate bigquery schema
        bigquery_schema = ','.join([':'.join(x) for x in bigquery_schema(var_set)]) 

        script_filename = tsv_out.replace("tsv", "bigquery_load.sh") 

        alert_script(script_filename, load_bigquery.format(**locals()))
        #Generate bcftools query
        with gzip.open(tsv_out, "wb") as f:
            for line in bcftools_query(var_set):
                f.write(line + "\n")
    with indent(4):
        puts(colored.blue("\nTSV Output Complete\n"))