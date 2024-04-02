import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import pickle5 as pickle
import io
import json
import boto3
import os

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def extract_cumsum_request(process_mode, request, s3_client, bucket_name):
    if process_mode == 0:
        prev = pickle.loads(request.cumsum_frame_data.trajectory_element)
        next = pickle.loads(request.cumsum_frame_data.transform)
    elif process_mode == 1:
        cumsum_request_json_data = s3_client.get_object(Bucket=bucket_name, Key=request.cumsum_request_json_key)['Body'].read().decode("utf-8")
        cumsum_request_data = json.loads(cumsum_request_json_data)
        prev = cumsum_request_data['trajectory_element']
        next = cumsum_request_data['transform']
    return prev, next

def construct_cumsum_response(sum, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        sum_bytes = pickle.dumps(sum)
        result = {'sum': sum_bytes}
    elif process_mode == 1:

        cumsum_response_data = {
            'sum': sum
        }

        cumsum_response_json_data = json.dumps(cumsum_response_data)
        cumsum_response_json_data_bytes = cumsum_response_json_data.encode("utf-8")
        cumsum_response_json_data_file = io.BytesIO(cumsum_response_json_data_bytes)

        key = "cumsum_response_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=cumsum_response_json_data_file)
        result = {'cumsum_response_json_key': key}
    return result

class CumSumService(pb2_grpc.CumSumServicer):

    def __init__(self, *args, **kwargs):
        pass

    def CumSum(self, request, context):
        process_mode = request.process_mode

        if process_mode == 1:
            aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
            aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
            s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
            bucket_name = "respect-dev-1"
        else:
            s3_client = None
            bucket_name = None

        prev, next = extract_cumsum_request(process_mode, request, s3_client, bucket_name)

        sum = [i + j for i, j in zip(prev, next)]
        result = construct_cumsum_response(sum, process_mode, s3_client, bucket_name)
        return pb2.CumSumResponse(**result)

def serve():
    cumsum_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_CumSumServicer_to_server(CumSumService(), cumsum_server)
    cumsum_server.add_insecure_port('[::]:50053')
    cumsum_server.start()
    cumsum_server.wait_for_termination()


if __name__ == '__main__':
    serve()