import streamlit as st
import base64
import PyPDF2 as pdf
import oci
# from streamlit_tags import st_tags
from langchain.chains import LLMChain
from langchain_community.llms import OCIGenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import re
import os
from langchain_community.embeddings import OCIGenAIEmbeddings
from langchain_community.vectorstores import FAISS

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Load secrets from Streamlit
CONFIG_PROFILE = st.secrets["CONFIG_PROFILE"]
NAMESPACE = st.secrets["NAMESPACE"]
BUCKET_NAME = st.secrets["BUCKET_NAME"]
OBJECT_NAME = st.secrets["OBJECT_NAME"]
COMPARTMENT_ID = st.secrets["COMPARTMENT_ID"]
user = st.secrets["user"]
fingerprint = st.secrets["fingerprint"]
key_file = st.secrets["key_file"]
tenancy = st.secrets["tenancy"]
region = st.secrets["region"]

# OCI configuration
config = {
    "user": user,
    "fingerprint": fingerprint,
    "key_file": key_file,
    "tenancy": tenancy,
    "region": region
}

pdf_upload_folder_path = "./Uploaded_resumes/"
text_file_location = "./Generated_text_from_resumes/"

def initialize_llm(temperature=0, top_p=0, top_k=0, max_tokens=2000):
    try:
        client = oci.generative_ai_inference.GenerativeAiInferenceClient(config=config)
        llm = OCIGenAI(
            model_id="cohere.command",
            service_endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
            compartment_id=COMPARTMENT_ID,
            model_kwargs={"temperature": temperature, "top_p": top_p, "top_k": top_k, "max_tokens": max_tokens},
            client=client
        )
    except Exception as e:
        st.error(f"Error initializing OCIGenAI: {e}")
        raise e

    return llm

def get_model_response(llm, text, description,retriever):
    template = """
    Act like a skilled or very experienced ATS (Application Tracking System)
    with a deep understanding of the tech field, software engineering, data science, data analysis,
    and big data engineering. Your task is to evaluate the resume based on the given job description.
    You must consider the job market is very competitive and you should provide
    the best assistance for selecting the resume. Assign the percentage Matching based
    on Job description and the missing keywords in resume by comparing job description with high accuracy also give the matching keywords with high accuracy 
    and also give the reason for the percentage match in bullet points with higher accuracy.
    also Match the job title with high accuracy.
    If any job profile resume is not matching with the job description then simply say not matching the job description 
    resume: {resume}
    description: {description}

    I want the response in one single string having the structure:
    Job description Match: %,

    \n\n
    Job Title Match:"",

    \n\n
    Matching Keywords:"",

    \n\n
    Missing Keywords:"",

    \n\n
    Profile Summary: "in bullet points"

    \n\n
    Reason for percentage match: "in bullet points"
    """

    prompt = PromptTemplate.from_template(template)

    chain = (
                    {"resume": retriever, "description": RunnablePassthrough()}
                    | prompt
                    | llm
                    | StrOutputParser()
            )
    # chain = LLMChain(llm=llm, prompt=prompt)
    response = chain.invoke(description)
    return response

def input_pdf_text(uploaded_file):
    reader = pdf.PdfReader(uploaded_file)
    text = ""

    for page in range(len(reader.pages)):
        page = reader.pages[page]
        text += str(page.extract_text()) + "\n"

    return text

# Function to save text to file
def save_text_to_file(text, file_path):
    with open(text_file_location+file_path, 'w', encoding='utf-8') as text_file:
        text_file.write(text)
    print("Text file created successfully.")

def extract_percentage(response_text):
    match = re.search(r'Job description Match:\s*(\d+)%', response_text)
    if match:
        return int(match.group(1))
    return 0

def is_job_title_matching(response_text):
    match = re.search(r'\*\*Job Title Match:([^\n]*)', response_text)
    print("type",type(match))
    print(match)
    # if match and "does not match the job title" not in match.group(1).strip().lower() or "not matching the job description" not in match.group(1).strip().lower():
    #     return True
    # return False

def extract_info(response):
    job_desc_match = re.search(r'Job description Match:\s*(\d+)%', response)
    job_title_match = re.search(r'Job Title Match:\s*(.*)', response)
    matching_keywords = re.search(r'Matching Keywords:\s*(.*)', response)
    missing_keywords = re.search(r'Missing Keywords:\s*(.*)', response)
    profile_summary = re.search(r'Profile Summary:\s*(.*)', response, re.DOTALL)
    reason_for_match = re.search(r'Reason for percentage match:\s*(.*)', response, re.DOTALL)
    
    info = {
        "Job description Match": job_desc_match.group(1) if job_desc_match else None,
        "Job Title Match": job_title_match.group(1).strip() if job_title_match else None,
        "Matching Keywords": matching_keywords.group(1).strip() if matching_keywords else None,
        "Missing Keywords": missing_keywords.group(1).strip() if missing_keywords else None,
        "Profile Summary": profile_summary.group(1).strip().replace('\n', ' ') if profile_summary else None,
        "Reason for percentage match": reason_for_match.group(1).strip().replace('\n', ' ') if reason_for_match else None
    }
    
    return info

def create_folder(pdf_upload_folder_path):
    # Specify the path for the new folder
    # pdf_upload_folder_path = "./Uploaded_resumes/."

    # Check if the folder already exists
    if not os.path.exists(pdf_upload_folder_path):
        # Create the directory
        os.makedirs(pdf_upload_folder_path)
        print(f"Folder created at: {pdf_upload_folder_path}")
    else:
        print(f"Folder already exists at: {pdf_upload_folder_path}")


def show_pdf(file_path):
    with open(file_path,"rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')

    pdf_display = F'<iframe src ="data:application/pdf;base64,{base64_pdf}" width ="100%" height = "1000" type = "application/pdf"</iframe>'
    st.markdown(pdf_display,unsafe_allow_html=True)


def clean_list(my_list):
    # Trim empty strings and strip spaces
    cleaned_list = [value.strip() for value in my_list if value.strip()]
    return cleaned_list

def tag(text, color):
    return f'<span class="tag" style="background-color:{color}; color:white; padding: 3px 5px 5px 5px; margin: 6px; border-radius: 5px;">{text}</span>'


# Streamlit app
st.title("Smart ATS")
st.text("Compare Resume with Job description ATS")
jd = st.text_area("Paste the Job Description",height = 200)
uploaded_files = st.file_uploader("Upload Your Resumes", type="pdf", accept_multiple_files=True, help="Please upload the pdf files")

submit = st.button("Submit")

if submit:
    if uploaded_files is not None:
        llm = initialize_llm(temperature=0)
        matching_responses = []
        non_matching_responses = []
        create_folder(pdf_upload_folder_path)
        create_folder(text_file_location)

        for uploaded_file in uploaded_files:
            try:
                filename = uploaded_file.name
                with st.expander(f"Response for {filename}",expanded=True):
                    # print(uploaded_file.name)
                    uploaded_file_name = uploaded_file.name
                    Save_pdf_file_path = pdf_upload_folder_path+uploaded_file_name                

                    with open(Save_pdf_file_path,"wb") as f:
                        f.write(uploaded_file.getbuffer())           
                    

                    pdf_name_without_ext = uploaded_file_name.rstrip('.pdf')
                    print("pdf_name_without_ext",pdf_name_without_ext)

                    text = input_pdf_text(uploaded_file)

                    text_file_path = f"{pdf_name_without_ext}.txt"

                    # print("text_file_path",text_file_path)
            
                    # Save the extracted text to the text file
                    save_text_to_file(text, text_file_path)
                    

                    loader = TextLoader(text_file_location+text_file_path)
                    documents = loader.load()

                    # print("documents",documents)
                    if documents is not None:
                        text_splitter = RecursiveCharacterTextSplitter(
                            chunk_size=1000,
                            chunk_overlap=200,
                            length_function=len
                        )
                        chunks = text_splitter.split_documents(documents)

                        client = oci.generative_ai_inference.GenerativeAiInferenceClient(config=config)
                        embeddings = OCIGenAIEmbeddings(
                            model_id="cohere.embed-english-light-v3.0",
                            service_endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
                            compartment_id="ocid1.compartment.oc1..aaaaaaaalnzl6zjv5aarhl32amczyeqwl7ahxnzqxwjpzppb74e7ubouzn4a",
                            client=client
                        )

                        VectorStore = FAISS.from_documents(chunks, embeddings)
                        retriever = VectorStore.as_retriever()
                        response = get_model_response(llm, text, jd,retriever)
                        
                        # with st.expander(f"Response for {filename}",expanded=True):
                        show_pdf(Save_pdf_file_path)
                        st.write(response)
                        print("response type",type(response))
                        info = extract_info(response)
                        # for key, value in info.items():
                        #     print(f"{key}: {value}")

                        Matching_Keywords = info.get("Matching Keywords").split(",")
                        Missing_Keywords = info.get("Missing Keywords").split(",")

                        keywords_green = clean_list(Matching_Keywords)
                        keywords_red = clean_list(Missing_Keywords)

                        # st.write("keywords_green",keywords_green)
                        # st.write("keywords_red",keywords_red)                      

                        # Create a container div for green tags
                        green_tags_container = '<div style="display: flex; flex-wrap: wrap;">'

                        # Add green tags to the container
                        for keyword in keywords_green:
                            green_tags_container += tag(keyword, 'green')

                        # Close the green tags container div
                        green_tags_container += '</div>'

                        # Create a container div for red tags
                        red_tags_container = '<div style="display: flex; flex-wrap: wrap;">'

                        # Add red tags to the container
                        for keyword in keywords_red:
                            red_tags_container += tag(keyword, 'red')

                        # Close the red tags container div
                        red_tags_container += '</div>'

                        # Display the green tags container
                        st.subheader("Matching keywords")
                        st.markdown(green_tags_container, unsafe_allow_html=True)

                        # Display the red tags container
                        st.subheader("Missing keywords")
                        st.markdown(red_tags_container, unsafe_allow_html=True)                                                

            except Exception as e:
                st.error(e)
                print(e) 

            # percentage = extract_percentage(response["text"])
            
        #     if is_job_title_matching(response["text"]):
        #         matching_responses.append((uploaded_file.name, response["text"], percentage))
        #     else:
        #         non_matching_responses.append((uploaded_file.name, response["text"], percentage))
        
        # # Sort responses based on the percentage match
        # matching_responses.sort(key=lambda x: x[2], reverse=True)
        
        # st.header("Matching Candidates")
        # for filename, response_text, percentage in matching_responses:
        #     with st.expander(f"Response for {filename} - Match: {percentage}%"):            
        #         st.subheader(f"Response for {filename}")
        #         st.write(response_text)
        
        # st.header("Non-Matching Candidates")
        # for filename, response_text, percentage in non_matching_responses:
        #     with st.expander(f"Response for {filename} - Not Matching"):
        #         st.subheader(f"Response for {filename}")
        #         st.write(response_text)