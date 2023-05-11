import pickle
from video_stabilizer_proto.video_stabilizer_pb2 import SmoothRequest
from video_stabilizer_clients.smooth_client import SmoothClient

class Smooth(object):
    def __init__(self,process_mode):
        self.client = SmoothClient()
        self.process_mode = process_mode

        
    def smooth(self, transforms_element, trajectory_element, trajectory):
        if self.process_mode == 0:
            return self.smooth_grpc(transforms_element, trajectory_element, trajectory)
        else:
            raise NotImplementedError

    def smooth_grpc(self, transforms_element, trajectory_element, trajectory):
        # convert arguments to bytes
        transforms_element = pickle.dumps(transforms_element)
        trajectory_element = pickle.dumps(trajectory_element)
        trajectory=pickle.dumps(trajectory)

        # call the client and get the response
        response = self.client.smooth(
            SmoothRequest(
                transforms_element=transforms_element,
                trajectory_element=trajectory_element,
                trajectory=trajectory
            )
        )

        # convert response to python objects
        final_transform = pickle.loads(response.final_transform)

        return final_transform

