import pickle
from video_stabilizer_proto.video_stabilizer_pb2 import SmoothRequest
from video_stabilizer_clients.smooth_client import SmoothClient

class Smooth(object):
    def __init__(self):
        self.client = SmoothClient()

    def smooth(self, transforms_element, trajectory_element, trajectory):
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
