🧠 Bioinsight AI Chatbot Prototype Documentation
================================================

**Version:** 2.4.0
**Project:** Biomedical data discovery and exploration BDF Task Area 3
**Last Updated:** July 2025

## 📌 Overview
This is an **early-stage prototype** of a chatbot built to help users explore biomedical data using natural language queries. The chatbot aims to support intuitive discovery and summarization of public cancer data by allowing users to ask questions in plain English instead of manually querying APIs or browsing filters.

## ⚙️ Capabilities (Current Release)
The prototype is designed to:
- Answer  **natural language queries** related to data from select biomedical resources and databases.
- Identify relevant studies, disease types, and experimental strategies.
- Allow basic **filtering by program, study, disease, and analyte.**
- Provide visual **summaries and counts** of available datasets.
- Perform correlation analysis of protein and/or gene expression data and visualize through plots and heatmaps.
- Assist researchers in discovering **what data exists** and **how it's structured** without needing technical expertise.

## 📂 Data Sources Currently Used
### Cancer Research Data Commons (CRDC)
- **Proteomic Data Commons (PDC)**
- **Genomic Data Commons (GDC)**
- **Imaging Data Commons (IDC)**
#### ProteomeXchange Resources
- **PRIDE**
#### Additional Repositories
- **Metabolomics Workbench (MWB)** – for metabolomics data  

**⚠️ Note:** Integration with these sources is a work in progress. Not all resources are fully connected yet. Responses may vary depending on data availability and current coverage.

## ⚠️ Assumptions and Known Limitations
Our chatbot integrates multiple data sources (e.g., CRDC, PX, MWB), bringing rich information access via a natural language interface. However, there are a few limitations to keep in mind:
- **Selective API Integration**
Not all available APIs are implemented. Integration is use case–driven, focusing on what’s most valuable and practical within the project’s scope.
- **Different APIs, Different Structures**
Each data source is unique in how it structures and provides information. The chatbot adjusts, but results can vary based on data format and API design.
- **Multiple Ways to Answer Similar Questions**
The agentic architecture can choose different paths or API calls depending on how a question is asked, which might lead to slightly different results for similar prompts.
- **Large API Responses**
Some endpoints return a lot of data, which can:
	- Slow down the response
	- Hit system token or timeout limits
	- Require trimming or summarization
- **Context and Memory Management**
For more complex or multi-step queries, maintaining sufficient context across turns is challenging, especially in a multi-agent setup.
- **Metadata Gaps**
Missing or inconsistent metadata can limit how detailed or accurate some answers are, particularly for complex data queries.
- **Natural Language vs. API Expectations**
The chatbot sometimes needs to translate broad, human-friendly questions into API-specific queries, which isn’t always straightforward.

## 💬 Example Use Cases and Questions
These are example prompts you can paste into the Bioinsight chatbot to explore multi-omic and imaging data across integrated biomedical datasets. 
________________________________________
### **🧠 Multi-Omics Data Exploration**
#### **🔬 GBM & Cross-Study Discovery (PDC & GDC)**
- _Can you provide information on any available GBM datasets in the PDC?_
- _Which molecular data types are available for GBM datasets in the GDC and PDC?_
- _Can you compare two GBM studies and summarize their key differences in methodology and data?_

#### **📈 Study-Level Insights & Visualization**
- _Generate a pie chart showing the demographic distribution (gender, age, ethnicity) in Study PDC000552._
- _Create a stacked bar chart for tumor stage and tissue origin in Study PDC000250._

#### **🧬 Gene Expression Visualization (via GDC)**
- _Show gene expression for CDKN2A, MDM2, MDM4, and TP53 in Study PDC000173._
- _Generate a violin plot for CDKN2A, MDM2, and TP53 expression in Study PDC000173._
- _Create a heat map to visualize gene expression for CDKN2A, MDM2, and TP53 in Study PDC000173._

### **🧪 Metabolomics Workbench (MWB) Queries**
#### **📋 Study Retrieval & Filtering**
- _List all breast cancer studies in metabolomics workbench with their study IDs._
- _List all breast cancer studies in metabolomics workbench that focus on chemotherapy response_
- _Which chemotherapy drugs were used in study ST002976?_
#### **💊 Drug & Gene Context**
- _Can you provide information about Doxorubicin from metabolomics workbench?_
- _What genes are associated with Doxorubicin metabolism?_

### **🖼️ Imaging Data Commons (IDC) Queries**
#### **📦 Collection-Level Summary**
- _How many collections are hosted on IDC?_
- _List all the collections hosted on IDC._
- _How many body parts are represented across all IDC collections?_
- _List all body parts represented in IDC._
- _How many imaging modalities are present across IDC datasets?_
- _List all the imaging modalities used in IDC._
- _How many MRI sequences are present in IDC?_
- _List all MRI sequences available on IDC._
- _What is the download size of each IDC collection in GB?_
- _For each IDC collection, list the number of images and patients._
- _For each collection, count the number of modalities and body parts._
- _For each collection, list body parts, modalities, and series descriptions._

#### **🔍 Cohort & Image Queries**
- _How many male brain MRI images are hosted on IDC?_
- _How many brain MRI images of male patients older than 5 years are in IDC?_
- _Give me the patient IDs and study dates for all pediatric studies on IDC._
- _How many patients are there in the nsclc_radiomics collection?_
- _List all segmentation images in the nsclc_radiomics collection._
- _What IDC collections contain GBM images?_
- _What collections have lung CT images?_
- _Which collections have both PET and CT scans?_
- _Which MRI scanners were used across IDC datasets?_

#### **📥 Download-Ready Queries**
- _Download all T2-weighted breast MRI images from IDC._
- _Download all PET scans from lung cancer studies on IDC._
- _Download all brain MRI data from IDC._
- _Download only T2 and FLAIR scans from the upenn_gbm collection._
- _Download male patient data from the upenn_gbm collection._

#### **📊 Subgroup Analysis (e.g., upenn_gbm)**
- _For the upenn_gbm collection, how many patients, images, modalities, body parts, sequences, and scanners are there?_
- _List all modalities, body parts, sequences, and scanners in the upenn_gbm collection._
- _For the upenn_gbm collection, how many male and female patients are there?_
- _How many teenagers are in the upenn_gbm collection?_
- _For the upenn_gbm collection, how many patients are under 25, between 25 and 50, and over 50 years old?_
- _For the upenn_gbm collection, how many patients correspond to each scanner?_

### **📚 Additional Use Cases**
#### **🔗 External Repositories**
- _List colon cancer studies from ProteomeXchange._
- _Is peptide AEPLAFTFSHDYK found in study PXD057661?_
- _Find studies analyzing the metabolite glutamine in brain cancer across all platforms._

#### **🧠 Research Context**
- What are the analytical challenges in performing a pan-cancer analysis?_

## 🔍 What’s Next
We are continuing to expand our capabilities, including:
- Enhanced question understanding
- Deeper cross-study insights
- Federated search across additional data sources
- In-line citation and source verification for chatbot responses
- Visual summaries

## 🤝 Feedback & Contact
We welcome input! Please share:
- Questions the chatbot didn’t answer well
- Ideas for new features or data sources
- Suggestions for user documentation or onboarding

