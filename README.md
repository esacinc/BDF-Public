# BDF-Public

Public repository for the BDF Chatbot developed by ICF

## Requirements

Python version >= 3.10

Before using the app, need to obtain various authentications and set them in .env file such as the following
- ChainLit secret string that is used to sign the authentication tokens
- AWS access and secret keys
- AWS Knowledge Base ID
- Name of the table where conversations history will be saved if using authentication 

## Installation

1. Clone the repository
2. `cd BDF-Chainlit-Chatbot`
3. `pip install -r requirements.txt`

If running the app in local environment we suggest to create a virtual environment and run the app from there:


## Running

`chainlit run .\chatbot-server.py`