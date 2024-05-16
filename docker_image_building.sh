./bazelisk-1.15.0 build --build_python_zip //...

# Copies zip files to their respective directories before running docker files
sudo cp /workspaces/video-stabilizer/bazel-bin/video_stabilizer_server/flow_server/flow_server.zip /workspaces/video-stabilizer/video_stabilizer_server/flow_server/
sudo cp /workspaces/video-stabilizer/bazel-bin/video_stabilizer_server/cumsum_server/cumsum_server.zip /workspaces/video-stabilizer/video_stabilizer_server/cumsum_server/
sudo cp /workspaces/video-stabilizer/bazel-bin/video_stabilizer_server/smooth_server/smooth_server.zip /workspaces/video-stabilizer/video_stabilizer_server/smooth_server/
sudo cp /workspaces/video-stabilizer/bazel-bin/video_stabilizer_server/stabilize_server/stabilize_server.zip /workspaces/video-stabilizer/video_stabilizer_server/stabilize_server/
sudo cp /workspaces/video-stabilizer/bazel-bin/video_stabilizer/video_stabilizer.zip /workspaces/video-stabilizer/video_stabilizer/

# Build docker images
docker build -t base .
cd /workspaces/video-stabilizer/video_stabilizer_server/flow_server
docker build -t flow-server .
cd /workspaces/video-stabilizer/video_stabilizer_server/cumsum_server
docker build -t cumsum-server .
cd /workspaces/video-stabilizer/video_stabilizer_server/smooth_server
docker build -t smooth-server .
cd /workspaces/video-stabilizer/video_stabilizer_server/stabilize_server
docker build -t stabilize-server .
cd /workspaces/video-stabilizer/video_stabilizer/
docker build -t video-stabilizer .
cd /workspaces/video-stabilizer/