from dotenv import load_dotenv
import os

load_dotenv()

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER")
MODEL_NAME = os.getenv("MODEL_NAME")