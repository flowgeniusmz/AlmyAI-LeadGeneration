import streamlit as st
import openai
import time
import config.pagesetup as ps
from openai import OpenAI
import uuid
from tavily import TavilyClient
from bs4 import BeautifulSoup
import requests
from tempfile import NamedTemporaryFile


#0. Page Config
st.set_page_config("AlmyAI", initial_sidebar_state="collapsed", layout="wide")


ps.set_title("AlmyAI", "Lead Generation Assistant")
ps.set_page_overview("Overview", "**Lead Generation Assistant** generates leads based on zip code.")

#2. Variable Setup

openai.api_key = st.secrets.openai.api_key
assistant = st.secrets.openai.assistant_key
model = "gpt-4-1106-preview"
client = OpenAI(api_key=st.secrets.openai.api_key)
tavily_client = TavilyClient(api_key=st.secrets.tavily.api_key)
thread = client.beta.threads.create()
threadid = thread.id


def TavilyCompanySearch(varCompanyURL):
    # Create an instance of TavilyClient
    tavily_client = TavilyClient(api_key=st.secrets.tavily.api_key)

    # Call get_company_info on the instance
    searchresults = tavily_client.get_company_info(
        query=varCompanyURL,
        search_depth="advanced",
        max_results=10,
    )
    
    return searchresults


#1. Function Setup
def get_query(varZipCode):
    prompt_query = f"beauty clinics OR medical spas OR dermatologists OR cosmetic surgeons near {varZipCode} specializing in aesthetic treatments OR laser therapy contact information"
    return prompt_query

def TavilySearch(varZipCode):
    search_result = tavily_client.search(
        query=get_query(varZipCode=varZipCode),
        search_depth="advanced"
        
    )
    print(search_result)
    return search_result

def get_urls(varSearchResult):
    urls = [result['url'] for result in varSearchResult['results']]
    return urls

def get_webscrape(varURL):
    try:
        response = requests.get(varURL)
        soup = BeautifulSoup(response.content, 'html.parser')
        return str(soup)  # Convert BeautifulSoup object to a string
    except requests.RequestException as e:
        print(f"Error fetching {varURL}: {e}")
        return ""  # Return an empty string in case of an error

def upload_file(file_path):
    file = client.files.create(
        file=open(file_path, "rb"),
        purpose="assistants"
    )
    return file

def save_html_to_file(html_content, file_name):
    with open(file_name, "w", encoding="utf-8") as file:
        file.write(html_content)

#3. Session State Management
if "session_id" not in st.session_state: #used to identify each session
    st.session_state.session_id = str(uuid.uuid4())

if "run" not in st.session_state: #stores the run state of the assistant
    st.session_state.run = {"status": None}

if "messages" not in st.session_state: #stores messages of the assistant
    st.session_state.messages = []
    st.chat_message("assistant").markdown("Enter a zip code to start.")
if "retry_error" not in st.session_state: #used for error handling
    st.session_state.retry_error = 0

#4. Openai setup
if "assistant" not in st.session_state:
    openai.api_key = st.secrets.openai.api_key

    # Load the previously created assistant
    st.session_state.assistant = openai.beta.assistants.retrieve(st.secrets.openai.assistant_key)

    # Create a new thread for this session
    st.session_state.thread = client.beta.threads.create(
        metadata={
            'session_id': st.session_state.session_id,
        }
    )


# If the run is completed, display the messages
elif hasattr(st.session_state.run, 'status') and st.session_state.run.status == "completed":
    # Retrieve the list of messages
    st.session_state.messages = client.beta.threads.messages.list(
        thread_id=st.session_state.thread.id
    )

    for thread_message in st.session_state.messages.data:
        for message_content in thread_message.content:
            # Access the actual text content
            message_content = message_content.text
            annotations = message_content.annotations
            citations = []
            
            # Iterate over the annotations and add footnotes
            for index, annotation in enumerate(annotations):
                # Replace the text with a footnote
                message_content.value = message_content.value.replace(annotation.text, f' [{index}]')
            
                # Gather citations based on annotation attributes
                if (file_citation := getattr(annotation, 'file_citation', None)):
                    cited_file = client.files.retrieve(file_citation.file_id)
                    citations.append(f'[{index}] {file_citation.quote} from {cited_file.filename}')
                elif (file_path := getattr(annotation, 'file_path', None)):
                    cited_file = client.files.retrieve(file_path.file_id)
                    citations.append(f'[{index}] Click <here> to download {cited_file.filename}')
                    # Note: File download functionality not implemented above for brevity

            # Add footnotes to the end of the message before displaying to user
            message_content.value += '\n' + '\n'.join(citations)

    # Display messages
    for message in reversed(st.session_state.messages.data):
        if message.role in ["user", "assistant"]:
            with st.chat_message(message.role):
                for content_part in message.content:
                    message_text = content_part.text.value
                    st.markdown(message_text)


#st.selectbox("Cateogory", options=["Medspa", "Derm"])

if prompt := st.chat_input("Enter a zip code to start"):
    with st.chat_message('user'):
        st.write(prompt)
    query = get_query(prompt)
    searchresults = TavilySearch(query)
    urllist = get_urls(searchresults)
    msgs = []
    fileids = []
    for url in urllist:
        webdata = TavilyCompanySearch(url)

        # Save the web data to a text file
        file_name = f"webdata_{uuid.uuid4()}.txt"
        save_html_to_file(webdata, file_name)

        # Upload the file to OpenAI
        uploaded_file = upload_file(file_name)
        fileids.append(uploaded_file.id)
        # Add message to the thread with the file ID
        #msg = client.beta.threads.messages.create(
        #    thread_id=st.session_state.thread.id,
        #    role="user",
        #    content="Review the attached file",  # Sending file ID instead of web data
        #    file_ids=[uploaded_file.id]
        #)
        #msgs.append(msg)

    st.session_state.messages = fileids
    msg = client.beta.threads.messages.create(
        thread_id=threadid, 
        content="Review the file and identify any potential lead information or mention of any company or aesthetic laser related entity provider or servicer.",
        file_ids=fileids,
        role="user"
    )
    # Rest of the code

    # Do a run to process the messages in the thread
    st.session_state.run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread.id,
        assistant_id=st.session_state.assistant.id,
    )
    if st.session_state.retry_error < 3:
        time.sleep(1) # Wait 1 second before checking run status
        st.rerun()
                    
# Check if 'run' object has 'status' attribute
if hasattr(st.session_state.run, 'status'):
    # Handle the 'running' status
    if st.session_state.run.status == "running":
        with st.chat_message('assistant'):
            st.write("Thinking ......")
        if st.session_state.retry_error < 3:
            time.sleep(1)  # Short delay to prevent immediate rerun, adjust as needed
            st.rerun()

    # Handle the 'failed' status
    elif st.session_state.run.status == "failed":
        st.session_state.retry_error += 1
        with st.chat_message('assistant'):
            if st.session_state.retry_error < 3:
                st.write("Run failed, retrying ......")
                time.sleep(3)  # Longer delay before retrying
                st.rerun()
            else:
                st.error("FAILED: The OpenAI API is currently processing too many requests. Please try again later ......")

    # Handle any status that is not 'completed'
    elif st.session_state.run.status != "completed":
        # Attempt to retrieve the run again, possibly redundant if there's no other status but 'running' or 'failed'
        st.session_state.run = client.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread.id,
            run_id=st.session_state.run.id,
        )
        if st.session_state.retry_error < 3:
            time.sleep(3)
            st.rerun()

#https://medium.com/prompt-engineering/unleashing-the-power-of-openais-new-gpt-assistants-with-streamlit-83779294629f
#https://github.com/tractorjuice/STGPT
