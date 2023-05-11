import pickle
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
from video_stabilizer_clients.cumsum_client import CumSumClient

class CumSum(object):
    def __init__(self,process_mode):
        self.client = CumSumClient()
        self.process_mode = process_mode

    def cumsum(self, trajectory_element, transform)
        if self.process_mode == 0:
            return self.cumsum_grpc(trajectory_element, transform)
        else:
            raise NotImplementedError
        
    def cumsum_grpc(self, trajectory_element, transform):
        # convert arguments to bytes
        trajectory_element = pickle.dumps(trajectory_element)
        transform = pickle.dumps(transform)

        # call the client and get the response
        response = self.client.cumsum(
            pb2.CumSumRequest(
                trajectory_element=trajectory_element,
                transform=transform,
            )
        )

        # convert response to python objects
        sum = pickle.loads(response.sum)

        return sum
    




            
