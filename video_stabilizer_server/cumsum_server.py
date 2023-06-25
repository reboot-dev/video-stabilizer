import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import pickle5 as pickle
import requests
from minio import Minio

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024
def download_object(url):
    response = requests.get(url,timeout=10)
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Failed to download object from URL: {url}")
def get_process_mode(request):
    if request.HasField('trajectory_element'):
        return 0
    elif request.HasField('trajectory_element_url'):
        return 1
    else:
        return NotImplementedError
def extract_request(process_mode,request):
    if process_mode == 0:
        prev = pickle.loads(request.trajectory_element)
        next = pickle.loads(request.transform)
    elif process_mode == 1:
        prev = download_object(request.trajectory_element_url)
        next = download_object(request.transform_url)
    else:
        return NotImplementedError
    return prev,next

class CumSumService(pb2_grpc.CumSumServicer):

    def __init__(self, *args, **kwargs):
        pass

    def CumSum(self, request, context):
        # extract request
        process_mode = get_process_mode(request)
        prev, next = extract_request(process_mode,request)
        # logic
        sum = [i + j for i, j in zip(prev, next)]
        # construct response
        if process_mode == 0:
            result = {'sum':pickle.dumps(sum)}
        elif process_mode == 1:
            # make client
            client = Minio("play.min.io",
            access_key="Q3AM3UQ867SPQQA43P2F",
            secret_key="zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",)
            # Make 'respect' bucket if not exist.
            found = client.bucket_exists("respect")
            if not found:
                client.make_bucket("respect")

            sum_bytes = pickle.dumps(sum)
            result = client.put_object("respect", "sum", sum_bytes, len(sum_bytes))
            sum_url = client.get_presigned_url("GET","respect","sum",)
            result = {'sum_url': sum_url} 
        else:
            return NotImplementedError
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