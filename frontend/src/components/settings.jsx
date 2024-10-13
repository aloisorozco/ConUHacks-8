import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import io from 'socket.io-client';
import classes from "./main_view.module.css"
import 'bootstrap/dist/css/bootstrap.min.css'
import Swal from 'sweetalert2'


const VIDEO_URL = "http://127.0.0.1:5500/"

function updateTextInput(event, setter) {
    setter(event.target.value);
}

async function authenticatePerson(socket, personID){
    return new Promise((resolve, reject) =>{

        socket.emit('authenticate', Number(personID))

        socket.on('auth_sucess', (data)=>{
            resolve({call: "auth_sucess",
                    data: data})
        })
        socket.on('auth_failed', (data)=>{
            reject({call: "auth_failed",
                    data: data})
        })
        socket.on('auth_client_disconnected', (data)=>{
            reject({call: "auth_client_disconnected",
                    data: data})
        })
        socket.on('face_not_found', (data)=>{
            reject({call: "face_not_found",
                    data: data})
        })
        socket.on('target_lost', (data)=>{
            reject({call: "target_lost",
                    data: data})
        })
        socket.on('auth_in_progress', (data)=>{
            reject({call: "auth_in_progress",
                    data: data})
        })
    })
}


async function checkServerStatus() {

    return axios.get(VIDEO_URL + "status").then((res) => {
        return res
    }).catch((error) => {
        console.log(error)
        return false
    })

}

async function endStream(socket) {

    return new Promise((resolve, reject) => {
        socket.emit('end_stream')
        socket.on('stream_exit_res', (data) => {
            resolve(data)
        })
    })

}

async function initiateSDP(socket, ) {

    return new Promise((resolve, reject) => {
        socket.emit('negotiate_sdp')
        socket.on('sdp_token', (sdp) => { resolve({sdp_token: sdp}) })
    })
}

async function resolveSDP(socket, spd_answer) {

    return new Promise((resolve, reject) => {
        socket.emit('resolve_sdp', spd_answer)
        socket.on('rtc_success', (data) => { resolve(data)})
    })
}

function SettingsScreen(props) {

    const input_ref = useRef(null)

    const [numUnknownPpl, setNumUnknownPpl] = useState(0);
    const [estimatedPerson, setEstimatedPerson] = useState("");

    const [authAllowed, setAuthAllowed] = useState(false);

    const [webSocket, setWebSocket] = useState(null)
    const [start, setStart] = useState(false);

    useEffect(() => {
        if (!webSocket) {
            const socket = io(VIDEO_URL)
            setWebSocket(socket)

            return () => {
                socket.disconnect()
            }
        }
    }, [])

    // Daniel pls clean this up - you can make like a file or dict with all the code calls, and just genralise by reject and aceept
    async function auth_human() {
        setAuthAllowed(false)

        let call = null
        await authenticatePerson(webSocket, input_ref.current.value).then((res) => {

            call =  res.call
            Swal.fire({
                icon: "success",
                title: res.call,
                text: res.data,
                confirmButtonColor: '#0D6EFD'
            });

        }).catch((res) => {

            call =  res.call
            Swal.fire({
                icon: "error",
                title: res.call,
                text: res.data,
                allowOutsideClick: false,
                allowEscapeKey: false,
                confirmButtonColor: '#0D6EFD'
            });
        })

        if (call == "auth_client_disconnected"){
            setAuthAllowed(false)
        }else{
            setAuthAllowed(true)
        }

        
    }

    async function startStream() {
        let stat = await checkServerStatus()

        if (stat) {
            setStart(true)
            setAuthAllowed(true)

            let sdp_offer = null
            await initiateSDP(webSocket, rc.localDescription).then((data) => {
                sdp_offer = data.sdp_token
            })

            let rc = new RTCPeerConnection()

            rc.ondatachannel(e =>{
                rc.dc = e.channel
                rc.dc.onmessage = e => {
                    console.log("frame recieved")
                    props.sendData({
                        frame: e.data,
                        start: true,
                    })
                }
                rc.dc.onopen = e => {console.log("Connection Open'")}
            })

            rc.setRemoteDescription(sdp_offer)
            rc.createAnswer().then(a => rc.setLocalDescription(a));

            await resolveSDP(webSocket, rc.localDescription.sdp).then((data) => console.log(data))

        }else{
            Swal.fire({
                icon: "error",
                title: "Server Unavailable",
                text: "Make sure the server is on",
                confirmButtonColor: '#0D6EFD'
            });
        }
    }

    async function stopStream() {
        let end = await endStream(webSocket)

        if (end == 200) {
            setStart(false)
            setAuthAllowed(false)
            props.sendData({
                frame: null,
                start: false,
            })
        } else {
            console.log("Issue disconnecting from the stream - ch-ch-chat is this real??")
        }
    }

    return (
        <div className={`shadow mr-auto ${classes.settings_container}`}>

            <div className={classes.settings_selections}>
                <label id="conf" htmlFor="customRange1" className="form-label"># Unknown People detected: {numUnknownPpl} </label>
            </div>

            <div className={classes.settings_selections}>
                <label htmlFor="customRange2" className="form-label">Estimated Person: {estimatedPerson} </label>
            </div>


            <div className={`${classes.main_btn_container}`}>
                <div className={`${classes.ID_input}`}>
                    <input ref={input_ref} type="input" class="form-control" id="exampleInputID" aria-describedby="emailHelp" placeholder="ID of the person to authenticate" />
                </div>

                <button onClick={auth_human} type="button" className={`btn btn-success btn-lg`} disabled={!authAllowed}>Authenticate</button>

                {start ?
                    <button onClick={stopStream} type="button" className={`btn btn-primary btn-lg ${classes.main_btn}`}>Stop</button> :
                    <button onClick={startStream} type="button" className={`btn btn-primary btn-lg ${classes.main_btn}`}>Apply & Start</button>}

            </div>

        </div>
    )
}

export default SettingsScreen