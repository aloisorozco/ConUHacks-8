import socketio
import aiohttp_cors
import asyncio
import concurrent.futures
from detection.cv_capture import Capture
from aiohttp import web
import concurrent.futures

class Server():

    app = web.Application()
    sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='aiohttp', async_handlers=True)

    sio.attach(app)

    # Set up CORS for aiohttp
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
    })

    _camera = None
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    _mutex = asyncio.Lock()
    _auth_status = {"sid": None,
                    "status": "n/a"}

    def __init__(self, camera) -> None:
        Server._camera = camera
    
    @staticmethod
    async def capture_and_send():
        for encoded_frame in Server._camera.start_capture():
            await Server.sio.emit('frame', encoded_frame, room='super_secret_security_camera_broadcast')
            await Server.sio.sleep(0.01)

    @staticmethod
    async def lock_in_face(id):
        Capture.update_auth_target(id)
    
    @staticmethod
    def check_face_existance(sid, id):
        return Capture.check_face_present(id)
    
    @staticmethod
    def await_auth_results():
        res = Capture.notify_auth_res()
        return res
    

    @staticmethod
    async def handle_disconnect_stream_stop(sid):
        await Server._mutex.acquire()
        if sid == Server._auth_status["sid"] and Server._auth_status["sid"] != "finished":
            Server._camera.kill_auth_process("auth_client_disconnected", "Cleint that started the auth process disconnected mid-auth. Canceling auth.")# kill the auth_process
        
        Server._mutex.release()


    # this is not a socket opperation - just a standard HTTP request to see if server is alive
    async def status(request):
        return web.Response(status=200)
    

    @sio.on('authenticate')
    async def authenticate(sid, data):

        await Server._mutex.acquire()
        if Server._auth_status["sid"] is not None and Server._auth_status["status"] != "finished":
            await Server.sio.emit('auth_in_progress', "Another user has already started to auth", to=sid)
            Server._mutex.release()
            return

        else:
            Server._auth_status["sid"] = sid
            Server._auth_status["status"] = "started"

        Server._mutex.release()

        loop = asyncio.get_event_loop()

        check_res = await loop.run_in_executor(Server._executor, Server.check_face_existance, *(sid, data))
        if (check_res):
            Server.sio.start_background_task(Server.lock_in_face, data)
            auth_res = await loop.run_in_executor(Server._executor, Server.await_auth_results)

            if "super_secret_security_camera_broadcast" not in Server.sio.rooms(sid):
                print(auth_res['code'])
                await Server.sio.emit(auth_res['code'], auth_res['comment'])
            else:
                await Server.sio.emit(auth_res["code"], auth_res["comment"], to=sid)

        else:
            await Server.sio.emit('face_not_found', f'person with ID {data} does not exist', to=sid) 

        await Server._mutex.acquire()
        Server._auth_status["sid"] = sid
        Server._auth_status["status"] = "finished"
        Server._mutex.release()
            

    @sio.on('join_stream')
    async def join_stream(sid):
        print(f'----- {sid} joined security broadcast stream -----')
        await Server.sio.enter_room(sid, 'super_secret_security_camera_broadcast')
        await Server.sio.emit('join_stream_confirmation', 200, to=sid)


    @sio.on('connect')
    async def connect(sid, environ):
        print('Client connected:', sid)
        await Server.sio.emit('reply', f"status: 200")


    @sio.on('disconnect')
    async def disconnect(sid):
        print('Client disconnected:', sid)
        await Server.handle_disconnect_stream_stop(sid)

            
    @sio.on('end_stream')
    async def end_stream(sid):
        # Server._camera.set_end_stream(True) # Ends stream for everyone by killing model - idealy we will have model run all the time and broadcast video to a cloud server
        print(f'Ending Stream for {sid}')
        await Server.sio.leave_room(sid, 'super_secret_security_camera_broadcast')
        await Server.sio.emit('stream_exit_res', 200, to=sid)

        await Server.handle_disconnect_stream_stop(sid)

    # Factory app init to start backround process
    async def init_app(self):
        Server.sio.start_background_task(Server.capture_and_send)
        return Server.app

    # Add route to CORS
    status_route = app.router.add_get('/status', status)
    cors.add(status_route)