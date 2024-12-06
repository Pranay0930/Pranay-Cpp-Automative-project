import boto3
from pymongo import MongoClient
from botocore.config import Config
from django.conf import settings

# DynamoDB connection
session = boto3.Session(profile_name="MSCCLOUD-250738637992")
dynamodb = session.client('dynamodb')
dynamodb_resource = session.resource('dynamodb')

