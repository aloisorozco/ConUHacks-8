from ultralytics import YOLO
from detection.annotators import Annotators
from detection.mesh import FaceMesh
from detection.classes.obstacle import Obstacle
import detection.audio.tts as tts
from detection.face import Face
from detection.face_tracker import FaceTracker

import threading
import concurrent.futures
import cv2
import supervision as sv
import time
import base64


class Capture():

    _CONFIDENCE_THRESHOLD = 0.5
    _TIME_OUT = 2
    _speech_thread = None
    _authenticate_id = None

    _auth_res_mutex = threading.Lock()
    auth_res_condition = threading.Condition(_auth_res_mutex)

    _auth_res = {"auth_passed": None,
                 "comment": None}

    mutex = threading.Lock()
    _faces_dict_mutex = threading.Lock()
    _dict_udpated_condition = threading.Condition(_faces_dict_mutex)
    _dict_shared = {}
    

    def __init__(self, args) -> None:

        frame_width, frame_height = args.webcam_resolution

        # change to 1 for webcam - if you have another device connected, otherwise leave at 0 for your default webcam
        # Capture vide + load model
        self.cap = cv2.VideoCapture(0)
        # self.model = YOLO("yolov8n.pt")
        self.model = YOLO("faces_30.pt")
        self.model.fuse()

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)

        self.annotators = Annotators(args.webcam_resolution)

        self.end_stream = False
        
        # Load TTS and FaceMesh models
        # self.speech = tts.TTS()
        self.face_mesh = FaceMesh(self, self.cap)

        self.faces_tracker = FaceTracker()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

        self.auth_timeout_timer = None


    @staticmethod
    def update_auth_res(auth_res, comment):
        Capture.auth_res_condition.acquire()

        Capture._auth_res["code"] = auth_res
        Capture._auth_res["comment"] = comment

        Capture.auth_res_condition.notify()
        Capture.auth_res_condition.release()


    @staticmethod
    def notify_auth_res():
        Capture.auth_res_condition.acquire()
        Capture.auth_res_condition.wait()

        res = Capture._auth_res

        Capture.auth_res_condition.release()

        return res

    @staticmethod   
    def check_face_present(face_id):
        Capture._dict_udpated_condition.acquire()
        Capture._dict_udpated_condition.wait()

        res = face_id in Capture._dict_shared 

        Capture._dict_udpated_condition.release()

        return res


    @staticmethod
    def update_auth_target(id):
        Capture.mutex.acquire()
        Capture._authenticate_id = id
        Capture.mutex.release()


    @staticmethod
    def get_auth_id():
        Capture.mutex.acquire()
        id = Capture._authenticate_id
        Capture.mutex.release()

        return id


    def save_faces_post_processing(self):
        Capture._dict_udpated_condition.acquire()

        self.faces_tracker.swap_dict()
        self.faces_tracker.add_new_faces_to_dict()

        Capture._dict_shared = self.faces_tracker.face_dict # TODO: May need to do a deep copy just to be safe
        
        Capture._dict_udpated_condition.notify()
        Capture._dict_udpated_condition.release()


    def kill_auth_process(self, code, reason):
        if self.auth_timeout_timer:
            self.auth_timeout_timer.cancel()

        self.auth_timeout_timer = None
        self.face_mesh.reset_auth()
        Capture.update_auth_target(None)
        Capture.update_auth_res(code, reason)

    def _speak_messages(self, obstacles):
        for obstacle in obstacles:
            self.speech.generate_and_play(obstacle.__str__())


    def encode_image(self, image):
        _, buffer = cv2.imencode('.jpg', image)
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        return jpg_as_text
    

    def set_end_stream(self, val):
        self.end_stream = val

    def start_capture(self):
       
        face_mesh_future = None
        faces_post_process_future = None

        cached_frame = None

        succ, frame = self.cap.read()
        if not succ:
            print("frame not returned - exiting")
            raise RuntimeError("Failed to read frame from source")

        result = self.model(frame, agnostic_nms=True, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(result)
        labels = []

        if(faces_post_process_future):
            faces_post_process_future.result() # We need this suprocess to block until completion to avoid race conditions on the next frame processing

        face_found = False

        for xyxy, _, _, class_id, _, _ in detections:
            entity_type = self.model.names[class_id]

            res = None
            if entity_type == "face":
                
                res = self.faces_tracker.re_index_faces(xyxy)

                auth_id = Capture.get_auth_id()

                if(auth_id is not None and res[0] and res[1] == auth_id):
                    
                    face_found = True
                    if not self.auth_timeout_timer:
                        print(f"~~~~~~~~ Begining Authentication procedure for the Person with Face ID {auth_id}")
                        self.face_mesh.gen_blink_sequence()

                        self.auth_timeout_timer = threading.Timer(interval=5.0, function=self.face_mesh.start_timeout)
                        self.auth_timeout_timer.start()

                    
                    target_face_img = frame[int(xyxy[1]):int(xyxy[3]), int(xyxy[0]):int(xyxy[2])] # only processing the section of the frame which is the person's face
                    face_mesh_future = self.thread_pool.submit(self.face_mesh.process_frame_face_mesh, target_face_img, (xyxy[0], xyxy[1]))

                if(not res[0]):
                    new_face = Face(xyxy)
                    self.faces_tracker.new_faces[new_face.face_id] = new_face

            labels.append(f"{entity_type} ID:{res[1] if res else -1}")

        faces_post_process_future = self.thread_pool.submit(self.save_faces_post_processing)

        if not face_found and self.auth_timeout_timer:
            self.kill_auth_process("target_lost", "Target Face was lost - please move back into frame, hold still and re-authenticate")
        
        # time_red = time.time()

        # obstacles = [
        #     Obstacle(self.model.names[class_id],
        #              confidence, xyxy, self.annotators.zone_polygon, time_red)
        #     for xyxy, _, confidence, class_id, _, _ in detections
        # ]

        # render only objects that are still on screen
        # time_now = time.time()
        # obstacles_to_speak = [
        #     obstacle for obstacle in obstacles if obstacle is not None and time_now - obstacle.time_registered < TIME_OUT]
        # # submit task to thread pool
        # self.executor.submit(self._speak_messages, obstacles_to_speak)

        # if (Capture._speech_thread == None or not Capture._speech_thread.is_alive()):
        #     obstacles_to_speak = [obstacle for obstacle in obstacles if obstacle != None and time.time(
        #     ) - obstacle.time_registered < Capture._TIME_OUT]
        #     Capture._speech_thread = threading.Thread(
        #         target=self._speak_messages, args=(obstacles_to_speak,))
        #     Capture._speech_thread.start()

        frame = self.annotators.bb_annotator.annotate(
            scene=frame,
            detections=detections
        )

        frame = self.annotators.label_annotator.annotate(
            scene=frame,
            detections=detections,
            labels=labels
        )

        self.annotators.zone.trigger(detections=detections)            
        # frame = self.annotators.zone_annotator.annotate(scene=frame)

        if(face_mesh_future):
            cached_frame = frame.copy()
            coords_to_draw, auth_finished = face_mesh_future.result()
            self.face_mesh.draw(frame, coords_to_draw)

            # TODO: Make sure this does not cause the capture thread to block - stress test it
            if auth_finished or not face_found:
                frame = cached_frame
                Capture.update_auth_target(None)

            for _, face in self.faces_tracker.face_dict.items():
                x = int(face.face_center_params[0])
                y = int(face.face_center_params[1])
                cv2.circle(frame, (x,y), radius=5, color=(0, 0, 255), thickness=4) #red

                new_center = face.predict()
                new_x = int(new_center[0])
                new_y = int(new_center[1])

                cv2.circle(frame, (new_x, new_y), radius=5, color=(255, 0, 0), thickness=4) #blue


        return self.encode_image(frame)

        # cv2.imshow("Sight Sence - Frame", frame)

        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break

    
    def cleanUp(self):
        # Release the capture object and close all windows
        self.cap.release()
        cv2.destroyAllWindows()
        self.thread_pool.shutdown()
        self.face_mesh.ptp()