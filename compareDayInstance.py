
import os, logging, logging.config, json, os.path, argparse, calendar, time
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import *
from dateutil import tz

def do_compare(prev_pickle_filename, curr_pickle_filename):
    prev_df = pd.read_pickle(prev_pickle_filename)
    curr_df = pd.read_pickle(curr_pickle_filename)

    #prev_df = prev_df.rename(columns=lambda x: x+'_prev')
    #prev_df = prev_df.rename(columns={'instance_id_prev':'instance_id'})
    prev_df = prev_df.rename(columns={'quantity':'quantity_prev','cost':'cost_prev','rated_cost':'rated_cost_prev','rateable_quantity':'rateable_quantity_prev'})
    #prev_df = prev_df.rename(columns={'cost':'cost_prev'})


    print(prev_df)
    print(curr_df)

    print(prev_df.columns)


    #combine_df = pd.merge(curr_df,prev_df[['instance_id','cost_prev']],on='instance_id', how='left')
    combine_df = pd.merge(curr_df,prev_df[['instance_id','metric','unit','unit_name','quantity_prev','cost_prev']], how='left')

    print(combine_df)
    print(combine_df.columns)

    print(combine_df[['instance_id','cost_prev','cost','quantity_prev','quantity']])

    combine_df['cost_diff'] = combine_df['cost'].sub(combine_df['cost_prev'])
    combine_df['quantity_diff'] = combine_df['quantity'].sub(combine_df['quantity_prev'])
    #print(combine_df[['instance_id','cost_diff','quantity_diff']])

    #instance_id_crn = 'crn:v1***'
    #final_df = combine_df[combine_df['instance_id'] == instance_id_crn]
    #print(final_df[['instance_id','cost_diff','quantity_diff']])
    print(combine_df[['instance_id','cost','cost_prev','quantity','quantity_prev','cost_diff','quantity_diff']])

    return combine_df

def createInstancesDetailTab(combine_df):
    """
    Write detail tab to excel
    """
    logging.info("Creating instances detail tab.")

    combine_df.to_excel(writer, "Instances_Detail")
    worksheet = writer.sheets['Instances_Detail']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:C", 12, format2)
    worksheet.set_column("D:E", 25, format2)
    worksheet.set_column("F:G", 18, format1)
    worksheet.set_column("H:I", 25, format2)
    worksheet.set_column("J:J", 18, format1)
    totalrows,totalcols=combine_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return


if __name__ == "__main__":
    #setup_logging()
    #load_dotenv()
    parser = argparse.ArgumentParser(description="Compare IBM Cloud Daily Usage.")
    parser.add_argument("--output", default=os.environ.get('output', 'compared.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--start", help="Start Month YYYYMMDD.")
    parser.add_argument("--end", help="End Month YYYYMMDD.")
    args = parser.parse_args()
    prev_date = args.start
    curr_date = args.end

    prev_pickle_filename = "instanceUsage-" + prev_date + ".pkl"
    curr_pickle_filename = "instanceUsage-" + curr_date + ".pkl"

    combine_df = do_compare(prev_pickle_filename, curr_pickle_filename)

    writer = pd.ExcelWriter(args.output, engine='xlsxwriter')
    workbook = writer.book
    createInstancesDetailTab(combine_df)
    writer.close()
