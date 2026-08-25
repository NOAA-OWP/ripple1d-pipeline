# Nomad Setup
1. Register image with a container registry,
```
cd tools/extent_library/
docker build -t extent-library .
docker tag extent-library registry.sh.nextgenwaterprediction.com/ngwpc/fim-c/flows2fim_extents:extent-library
docker login registry.sh.nextgenwaterprediction.com -u abdul.siddiqui -p <gitlab_token>
docker push registry.sh.nextgenwaterprediction.com/ngwpc/fim-c/flows2fim_extents:extent-library
```

2. Create a Parameterized Nomad Job Definition

3. Dispatch jobs through `dispatch_jobs.py