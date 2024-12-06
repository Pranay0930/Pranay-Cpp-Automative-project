from datetime import datetime
import json
from django.http import JsonResponse
from django.shortcuts import render
from .db_connections import dynamodb, dynamodb_resource
from botocore.exceptions import ClientError
import boto3

session = boto3.Session(profile_name="MSCCLOUD-250738637992")
sns_client = session.client('sns')
s3_client = session.client('s3')
rekognition_client = session.client('rekognition')
lambda_client = session.client('lambda')


def create_table_if_not_exists():
    table_name = "vehicles_list_with_labels"
    try:
        # Check if the table exists
        existing_tables = dynamodb.list_tables()["TableNames"]
        if table_name in existing_tables:
            print(f"Table '{table_name}' already exists.")
            return dynamodb_resource.Table(table_name)

        # If the table does not exist, create it
        table = dynamodb_resource.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    'AttributeName': 'id',  # Partition key
                    'KeyType': 'HASH'
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'id',
                    'AttributeType': 'N'  # Number for auto-increment id
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        print(f"Table '{table_name}' is being created. This may take a moment...")
        table.wait_until_exists()
        print(f"Table '{table_name}' created successfully.")
        return table
    except ClientError as e:
        print(f"Error: {e}")
        return None

table = create_table_if_not_exists()

def upload_image_to_s3(file, file_name):
    try:
        # Upload the file to S3
        bucket_name = "23201827-cpp"
        s3_client.upload_fileobj(file, bucket_name, file_name)

        s3_client.put_object_acl(
            Bucket=bucket_name,
            Key=file_name,
            ACL="public-read"
        )

        # Generate S3 URL
        s3_url = f"https://{bucket_name}.s3.us-east-1.amazonaws.com/{file_name}"
        return s3_url
    except Exception as e:
        print(f"Error uploading image to S3: {e}")
        return None

def detect_image_labels(bucket_name, file_name):
    try:
        # Call Rekognition to detect labels in the uploaded image
        response = rekognition_client.detect_labels(
            Image={
                'S3Object': {
                    'Bucket': bucket_name,
                    'Name': file_name
                }
            },
            MaxLabels=10
        )
        print(f"Response: {response}")
        labels = [label['Name'] for label in response['Labels']]
        print(f"Labels detected: {labels}")
        return labels
    except Exception as e:
        # print(f"Error detecting image labels: {e}")
        return "image"

def invoke_lambda_function(payload):
    try:
        # Invoke AWS Lambda for additional processing
        response = lambda_client.invoke(
            FunctionName="vehicles_add_operation",
            InvocationType="RequestResponse",
            Payload=payload
        )
        result = response['Payload'].read().decode('utf-8')
        print(f"Lambda response: {result}")
        return result
    except Exception as e:
        print(f"Error invoking Lambda function: {e}")
        return None

# Function to read all records from the table
from django.shortcuts import render
from django.http import JsonResponse

def read_all_items(request):
    if request.method == "GET":
        try:
            # Scan the DynamoDB table to get all items
            response = table.scan()
            items = response.get("Items", [])
            
            # Pass the items to the template
            return render(request, 'read_all_items.html', {'items': items})
        except Exception as e:
            print(f"Error reading items: {e}")
            return JsonResponse({"error": "Failed to fetch items."}, status=500)
    else:
        # Return a 405 Method Not Allowed for unsupported HTTP methods
        return JsonResponse({"error": "Method not allowed."}, status=405)



def update_item(request):
    if request.method == "POST":
        data = request.POST
        item_id=data.get("item_id")
        updated_name = data.get("item_name")
        updated_description = data.get("item_description")
        updated_image_url = data.get("image_url")
        updated_image_label = data.get("image_label")

        if not updated_name or not updated_description:
            return JsonResponse({"error": "Both item_name and item_description are required."}, status=400)

        try:
            # Update item in the table
            table.update_item(
                Key={"id": int(item_id)},
                UpdateExpression="""
                    SET item_name = :name, 
                        item_description = :desc, 
                        image_url = :img_url, 
                        image_label = :img_label
                """,
                ExpressionAttributeValues={
                    ":name": updated_name,
                    ":desc": updated_description,
                    ":img_url": updated_image_url,
                    ":img_label": updated_image_label,
                }
            )
            response = table.scan()
            items = response.get("Items", [])
            
            # Pass the items to the template
            return render(request, 'read_all_items.html', {'items': items})
            # return JsonResponse({"message": "Item updated successfully."}, status=200)
        except Exception as e:
            print(f"Error updating item: {e}")
            return JsonResponse({"error": "Failed to update item."}, status=500)
    return render(request, 'update_item.html', {"item_id": item_id})


# Function to delete a specific record in the table
def delete_item(request):
    if request.method == "POST":
        try:
            data = request.POST
            item_id=data.get("item_id")
            # Delete the item from the table
            table.delete_item(Key={"id": int(item_id)})
            response = table.scan()
            items = response.get("Items", []) 
            # Pass the items to the template
            return render(request, 'read_all_items.html', {'items': items})
        except Exception as e:
            print(f"Error deleting item: {e}")
            return JsonResponse({"error": "Failed to delete item."}, status=500)
    return render(request, 'delete_item.html', {"item_id": item_id})

def add_item(request):
    if request.method == "POST":
        data = request.POST
        item_name = data.get("item_name")
        item_description = data.get("item_description")
        file = request.FILES.get('item_image')
        file_name = f"{datetime.utcnow().isoformat()}.jpg"  # Unique filename

        response = table.scan(ProjectionExpression="id")
        ids = [int(item['id']) for item in response.get('Items', [])]  # Convert 'id' to integer
        new_id = max(ids, default=0) + 1
 

        # Step 1: Upload the image to S3
        image_url = upload_image_to_s3(file, file_name)

        if not image_url:
            return JsonResponse({"error": "Failed to upload image to S3."}, status=500)

        # Step 2: Detect labels using Rekognition
        bucket_name = "23201827-cpp"
        labels = detect_image_labels(bucket_name, file_name)

        if not item_name or not item_description:
            return JsonResponse({"error": "Both item_name and item_description are required."}, status=400)
        
        # Step 1: Invoke Lambda function for additional processing
        payload = {
            'id': new_id,
            'item_name': item_name,
            'item_description': item_description,
            'image_url': image_url,
            'image_label':", ".join(labels)
        }

        print(f"payload: {payload}")
        lambda_response = invoke_lambda_function(json.dumps(payload))

        response = sns_client.publish(
            PhoneNumber="918054810999",  # Replace with the recipient's phone number in E.164 format
            Message="Data Successfully Saved"
        )

        print(f"response: {response}")

        '''return JsonResponse({
            "message": "Item added successfully and processed by Lambda.",
            "lambda_response": lambda_response
        })'''
        return render(request, 'success.html')
        '''return render(request, 'page_success.html', {
            'item_name': item_name,
            'item_description': item_description,
            'image_url': image_url,
            'lambda_response': lambda_response
        })'''
    return render(request, 'add_item.html')