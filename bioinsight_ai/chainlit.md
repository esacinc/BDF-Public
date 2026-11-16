🧠 BioInsight AI Chatbot Public Preview
========================================
**Status:**  Public Preview (Exploratory)
**Project:** ARPA-H Biomedical Data Fabric
**Last Updated:** November 2026

## 📌 Overview
BioInsight is an exploratory, AI-enabled chatbot intended to support discovery and exploration of publicly available biomedical data using natural language queries. The tool allows users to ask questions in plain English to facilitate high-level exploration and summarization of public cancer datasets, rather than directly querying APIs or navigating complex data interfaces.
This Public Preview is provided for informational and exploratory purposes only. Functionality, responses, data coverage, and performance may change over time as the tool is further developed and refined.

## ⚙️ Capabilities (Current Release)
**BioInsight is designed to help researchers discover, explore, and make sense of complex cancer data across distributed public resources — using natural language.**

### 🔍 Discovery
- Discover what cancer data exists across diverse multiomic resources including proteomics, genomics, imaging, metabolomics and lipidomics.
- Identify relevant programs, studies, cohorts, and data types by disease, modality, or program.
- Understand where data lives and how it is organized, without navigating individual portals.

### 🧭 Exploration
- Explore study- and cohort-level metadata, including demographics, biospecimens, and experimental strategies.
- Compare studies within and across programs through conversational follow-ups.
- Maintain context across multi-step questions without needing technical knowledge of schemas or APIs.

### 📊 Visualization
- View interactive summaries, distributions, and cohort breakdowns.
- Visualize molecular data (expression plots, heatmaps) and survival trends (Kaplan–Meier).
- Discover and interact with imaging collections and derived visual outputs.

### 🧪 Analysis (Exploratory)
- Perform lightweight, exploratory analyses to assess dataset relevance.
- Support handoff to external tools and workflows for deeper analysis.

### 🎥 Demo Videos
Short demo videos showcasing BioInsight’s discovery, exploration, and visualization capabilities are available on our YouTube channel:
- Natural language discovery across proteomics, genomics, and imaging data
- Exploring cohorts, demographics, and study metadata
- Interactive molecular and imaging visualizations
- Cross-repository exploration and follow-up queries

**👉 Watch the demos:** [YouTube channel](https://www.youtube.com/@bioinsightai)

## 📂 Data Sources Currently Supported
BioInsight integrates and explores data from multiple public biomedical repositories, with a primary focus on cancer research data. Support spans **core CRDC resources, imaging collections**, and **external omics repositories**, with ongoing expansion.
### Cancer Research Data Commons (CRDC)
BioInsight provides deep, first-class support for select CRDC nodes:
- **Proteomic Data Commons (PDC)**
Mass spectrometry–based datasets from large cancer proteogenomic programs (e.g., CPTAC), including proteome, phosphoproteome, glycoproteome, ubiquitinome, acetylome, and select metabolomics and lipidomics data.
- **Genomic Data Commons (GDC)** 
Genomic, transcriptomic, and clinical data across major cancer programs (e.g., TCGA, TARGET, CPTAC), supporting cohort discovery, gene expression, and survival analysis.
- **Imaging Data Commons (IDC)** 
Cancer imaging collections and metadata supporting imaging discovery, filtering, visualization, and image-derived workflows.
#### 🖼️ Cancer Imaging Collections (Accessed via IDC & Imaging Workflows)
- **The Cancer Imaging Archive (TCIA)**
Public cancer imaging datasets accessible through IDC and associated imaging services.
- **Medical Imaging and Data Resource Center (MIDRC)**
Imaging collections and metadata accessed through shared imaging infrastructure and workflows.
#### 🌍 External Omics Repositories
- **ProteomeXchange Resources**
	- **PRIDE** – Proteomics datasets and metadata for discovery and contextual exploration.
- **Metabolomics Workbench (MWB)**
Metabolomics studies and metadata, with a focus on cancer-related datasets and treatment response.
 
## ⚠️ Integration Status
BioInsight is under active development. All listed sources are supported for **data discovery**, while the depth of exploration, visualization, and analysis varies by resource as integrations continue to mature.

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
These are example prompts you can paste into the BioInsight chatbot to explore multi-omic and imaging data across integrated biomedical datasets. 
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
- _How many body parts are represented across all IDC collections? List all of them_
- _How many imaging modalities are present across IDC datasets? List all of them_
- _How many MRI sequences are present in IDC?_
- _For each IDC collection, list the number of images and patients._
- _For each collection, count the number of modalities and body parts._

#### **🔍 Cohort & Image Queries**
- _How many male brain MRI images are hosted on IDC?_
- _How many brain MRI images of male patients older than 5 years are in IDC?_
- _How many patients are in all pediatric studies on IDC._
- _How many patients are there in the nsclc_radiomics collection?_
- _What IDC collections contain GBM images?_
- _What collections have lung CT images?_
- _Which collections have both PET and CT scans?_
- _Which MRI scanners were used across IDC datasets?_

#### **📊 Subgroup Analysis (e.g., upenn_gbm)**
- _For the IDC upenn_gbm collection, how many patients, images, modalities, body parts, sequences, and scanners are there?_
- _List all modalities, body parts, sequences, and scanners in the IDC upenn_gbm collection._
- _For the IDC upenn_gbm collection, how many male and female patients are there?_
- _How many teenagers are in the IDC upenn_gbm collection?_
- _For the IDC upenn_gbm collection, plot distribution of patient data by age using the following bins: under 25, between 25 and 50, and over 50 years old?_
- _For the IDC upenn_gbm collection, how many patients correspond to each scanner?_

### **📚 Additional Use Cases**
#### **🔗 External Repositories**
- _List colon cancer studies from ProteomeXchange._
- _Is peptide AEPLAFTFSHDYK found in study PXD057661?_
- _Find studies analyzing the metabolite glutamine in brain cancer across all platforms._

#### **🧠 Research Context**
- _What are the analytical challenges in performing a pan-cancer analysis?_

## 🔍 What’s Next
We are continuing to expand our capabilities, including:
- Enhanced question understanding
- Deeper cross-study insights
- Federated search across additional data sources
- In-line citation and source verification for chatbot responses
- Visual summaries

## 🤝 Feedback & Contact
We’d love to hear from you! If you have feedback, questions, or suggestions, feel free to reach out to us at <bioinsight-ai@icf.com>. Your input helps us improve BioInsight.

**Version:** 4.12.16
