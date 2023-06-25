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
    if request.HasField('transforms_element'):
        return 0
    elif request.HasField('transforms_element_url'):
        return 1
    else:
        return NotImplementedError
def extract_request(process_mode,request):
    if process_mode == 0:
        transform = pickle.loads(request.transforms_element)
        point = pickle.loads(request.trajectory_element)
        window = pickle.loads(request.trajectory)
    elif process_mode == 1:
        transform = download_object(request.transform_element_url)
        point = download_object(request.trajectory_element_url)
        window = download_object(request.trajectory_url)
    else:
        return NotImplementedError
    return transform,point,window

class SmoothService(pb2_grpc.SmoothServicer):

    def __init__(self, *args, **kwargs):
        pass
    
    # wip
    def Smooth(self, request, context):
        # extract request
        process_mode = get_process_mode(request)
        transform,point,window = extract_request(process_mode,request)
        # logic
        mean = np.mean(window, axis=0)
        smoothed = mean - point + transform
        # construct response
        if process_mode == 0:
            result = {'final_transform': pickle.dumps(smoothed)}
        elif process_mode == 1:
            # make MinIO client
            client = Minio(
            "play.min.io",
            access_key="Q3AM3UQ867SPQQA43P2F",
            secret_key="zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",
            )
            # Make 'respect' bucket if not exist.
            found = client.bucket_exists("respect")
            if not found:
                client.make_bucket("respect")
            # store in MinIO, get url
            final_transform_bytes = pickle.dumps(smoothed)
            result = client.put_object("respect", "final_transform", final_transform_bytes, len(final_transform_bytes))
            final_transform_url = client.get_presigned_url("GET","respect","final_transform",)
            result = {'final_transform_url': final_transform_url}
        else:
            return NotImplementedError

        return pb2.SmoothResponse(**result)

def serve():
    smooth_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_SmoothServicer_to_server(SmoothService(), smooth_server)
    smooth_server.add_insecure_port('[::]:50054')
    smooth_server.start()
    smooth_server.wait_for_termination()


if __name__ == '__main__':
    serve()