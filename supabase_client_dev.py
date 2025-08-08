import os
from supabase import create_client
from dotenv import load_dotenv


"""
PLEASE READ!!!!

    Please do not remove or use this file. This is for the chatbot only while the database is
    currently being developed and not intended for other use. 
    
    If you need to use the Supabase client, please refer to the main supabase_client.py file.
    
    By: raffa
    Date: 2023-10-04
    
PLEASE READ!!!!
"""


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_TESTING_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_TEST_ANON_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)