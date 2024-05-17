import os
from typing import Coroutine
from PIL import Image
from flask import Flask, request, Response, send_from_directory
from aiortc import RTCPeerConnection, RTCIceCandidate, MediaStreamTrack
import json
app = Flask(__name__)

servers = {
    "iceServers": [
        {
            "urls":['stun:stun3.l.google.com:19302',
            'stun:stun1.l.google.com:19302',
            'stun:stun2.l.google.com:19302'],
        },

    ],
    "iceCandidatePoolSize": 10,
}
pc = RTCPeerConnection(servers)

class CustomTrack(MediaStreamTrack):
    kind = 'video'
    def __init__(self):
        super.__init__()
        
    def recv(self):
        frame =  super().recv()
        print(frame)
        
        return frame
        
        


answer = None
@app.route('/x')
def index():
    return send_from_directory('static','index.html')



@app.route('/candidate',methods=['POST'])
async def candidate_add():
    try:
        candidate = request.get_json()
        try:
            await pc.addIceCandidate(candidate)
            return Response('Success added candidate!')
        except:
            return Response(status=400,response={"Couldn't handle candidate"})    
    except:
        return Response(status=400,response=json.dumps({"Parse error"}))

@app.route('/offer',methods=['POST'])
async def offer():
    try:
        offerData = request.get_json()
        
        try:
            await pc.setRemoteDescription(offerData)
            await pc.addTrack(CustomTrack())
            answer =await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            
            return Response(response={"type":"answer","answer":answer})
        except:
            return Response(status=400,response={"offer error"})    
    except:
        return Response(status=400,response={"parse error"})



if __name__ == '__main__':
    app.run(debug=os.getenv('DEBUG'),host='0.0.0.0')
