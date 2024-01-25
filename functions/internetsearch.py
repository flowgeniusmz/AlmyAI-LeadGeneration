import os
import streamlit as st
import json
import time
from tavily import TavilyClient

tavily_client = TavilyClient(api_key=st.secrets.tavily.api_key)


def get_query(varZipCode):
    prompt_query = f"beauty clinics OR medical spas OR dermatologists OR cosmetic surgeons near {varZipCode} specializing in aesthetic treatments OR laser therapy"
    return prompt_query



def TavilySearch(varZipCode):
    search_result = tavily_client.get_search_context(
        query=get_query(varZipCode=varZipCode),
        search_depth="advanced",
        max_tokens=8000
    )
    
    return search_result




