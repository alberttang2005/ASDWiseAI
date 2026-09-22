import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
# Explicit secret file outside source control; never auto-read repository .env files.
if os.getenv('ASDWISE_ENV_FILE'):load_dotenv(Path(os.environ['ASDWISE_ENV_FILE']).expanduser())
from .serverless import create_serverless_app
if __name__=='__main__':uvicorn.run(create_serverless_app(),host='127.0.0.1',port=int(os.getenv('ASDWISE_API_PORT','8001')),access_log=False)
