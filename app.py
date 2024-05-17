from contextlib import asynccontextmanager
import os
from typing import Coroutine
from PIL import Image
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from aiortc import VideoStreamTrack,RTCPeerConnection,RTCIceServer,RTCConfiguration,RTCSessionDescription, RTCIceCandidate, MediaStreamTrack
import json
import uvicorn
import asyncio
from av import VideoFrame
import numpy as np
from ai import detect_head_direction




def create_ice_candidate_from_json(candidate_data_json) -> RTCIceCandidate:
    candidate_parts = candidate_data_json['candidate'].split(' ')

    component = int(candidate_parts[1])
    foundation = candidate_parts[0].split(':')[1]
    ip = candidate_parts[4]
    port = int(candidate_parts[5])
    priority = int(candidate_parts[3])
    protocol = candidate_parts[2]
    type = candidate_parts[7]
    relatedAddress = None
    relatedPort = None
    sdpMid = candidate_data_json['sdpMid']
    sdpMLineIndex = candidate_data_json['sdpMLineIndex']
    tcpType = None

    ice_candidate = RTCIceCandidate(component, foundation, ip, port, priority, protocol, type, relatedAddress, relatedPort, sdpMid, sdpMLineIndex, tcpType)

    return ice_candidate
def create_offer_from_json(offer_json) -> RTCSessionDescription:
    sdp = offer_json['sdp']
    type = offer_json['type']
    offer = RTCSessionDescription(sdp=sdp, type=type)
    return offer


iceServers : list[RTCIceServer] =  [
    RTCIceServer(
        urls=['stun:stun3.l.google.com:19302',
              'stun:stun1.l.google.com:19302',
              'stun:stun2.l.google.com:19302']
    )
]
rtcConfig : RTCConfiguration = RTCConfiguration(iceServers=iceServers)

pc : RTCPeerConnection = RTCPeerConnection(configuration=rtcConfig)


class CustomTrack(VideoStreamTrack):
    kind = 'video'

    def __init__(self,input_track: MediaStreamTrack = None):
        super().__init__()
        self.track = input_track
        self.counter = 0

    async def recv(self):
        self.counter += 1
        frame = await self.track.recv()    

        img = frame.to_ndarray(format='bgr24')
        
         # Perform processing on the img using numpy
        processed_img = np.flip(img, axis=0)  # Example: flipping the image horizontally
        
         # Convert the processed_img back to VideoFrame
        processed_frame = VideoFrame.from_ndarray(processed_img, format='bgr24')
        
        processed_frame.pts = frame.pts
        processed_frame.time_base = frame.time_base
       


        return processed_frame

class AITrack(VideoStreamTrack):
    kind = 'video'

    def __init__(self,input_track: MediaStreamTrack = None):
        super().__init__()
        self.track = input_track
        self.counter = 0

    async def recv(self):
        self.counter += 1
        frame = await self.track.recv()    

        img = frame.to_ndarray(format='bgr24')
        
         # Perform processing on the img using numpy
        processed_img = detect_head_direction(img)  # Example: flipping the image horizontally
        
         # Convert the processed_img back to VideoFrame
        processed_frame = VideoFrame.from_ndarray(processed_img, format='bgr24')
        
        processed_frame.pts = frame.pts
        processed_frame.time_base = frame.time_base
       


        return processed_frame

    
answer = None
sender = None

def InitPC():
    iceServers : list[RTCIceServer] =  [
        RTCIceServer(
            urls=['stun:stun3.l.google.com:19302',
                'stun:stun1.l.google.com:19302',
                'stun:stun2.l.google.com:19302']
        )
    ]
    rtcConfig : RTCConfiguration = RTCConfiguration(iceServers=iceServers)

    pc : RTCPeerConnection = RTCPeerConnection(configuration=rtcConfig)
    answer = None
    sender = None
    
    
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            # Stop all tracks
            for sender in pc.getSenders():
                sender.track.stop()

            # Close the connection
            await pc.close()

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        print("ICE connection state is %s" % pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            # Stop all tracks
            for sender in pc.getSenders():
                sender.track.stop()

            # Close the connection
            await pc.close()
            answer = None
            sender = None

    @pc.on("track")
    def on_track(track):
        print("Track %s is added" % track.kind)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    InitPC()
    yield
    answer = None
    sender = None
    await pc.close()
    # Shutdown


app = FastAPI(lifespan=lifespan)
app.title ='video-processor-prototype'
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get('/',response_class=FileResponse)
async def index(request: Request):
    
    return FileResponse('static/index.html')
@app.get('/rtc',response_class=JSONResponse)
async def rtc(request: Request):
    print(pc.iceGatheringState)
    print(pc.connectionState)
    return JSONResponse(content={
        "title": app.title,
        'rtc': pc.connectionState
    })



@app.post('/candidate',response_class=JSONResponse)
async def candidate_add(request: Request):
    jsonObj = (await request.json())
    ice_candidate = create_ice_candidate_from_json(jsonObj)
    await pc.addIceCandidate(ice_candidate)
    return JSONResponse(content='Success added candidate!')


@app.post('/offer', response_class=JSONResponse)
async def offer(request: Request):
    jsonObj = (await request.json())
    
    offerData = create_offer_from_json(jsonObj)
    if(pc.signalingState == "closed"):
        return JSONResponse(content={"message":"Signaling state is closed!"}) 
    
    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        print("ICE connection state is %s", pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            await pc.close()
          

    @pc.on("track")
    def on_track(track):
        print("Track %s received", track.kind)

        if track.kind == "video":
            local_video = CustomTrack(track)
            pc.addTrack(local_video)

        @track.on("ended")
        async def on_ended():
            print("Track %s ended", track.kind)
          

    
    await pc.setRemoteDescription(offerData)
    
    answer = await pc.createAnswer()

    await pc.setLocalDescription(answer)



    return JSONResponse(content={"type": "answer", "answer":{
        "sdp": answer.sdp,
        "type": answer.type
    }})
    


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0')
