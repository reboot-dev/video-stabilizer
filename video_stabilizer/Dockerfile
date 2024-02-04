FROM base:latest

COPY video_stabilizer.zip app/
CMD ["python", "/app/video_stabilizer.zip", "--num-videos", "1", "--video-path", "/workspaces/video-stabilizer/video_example/husky.mp4", "--output-file", "/workspaces/video-stabilizer/video_stabilizer_output"]