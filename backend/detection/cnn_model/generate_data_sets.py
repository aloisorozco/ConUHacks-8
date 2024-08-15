# Here I will make a script to populate the auth file with pictures of me, downscaled to 105x105
# Easy stuff - will use opencv to save frames
import uuid
import cv2 as cv
import random
import os

AUTHED_DIR = "backend/detection/cnn_model/authed_people"
TRAIN_BAD_DIR = "backend/detection/cnn_model/train_raw"
TRAIN_CLEAN_DIR = "backend/detection/cnn_model/train"

VALID_BAD_DIR = "backend/detection/cnn_model/val_raw"
VALID_CLEAN_DIR = "backend/detection/cnn_model/val"

def collect_my_faces():
    cap = cv.VideoCapture(0)
    roi_x, roi_y, roi_w, roi_h = 480,900,400,425

    angle = 45 
    center = (105 // 2, 105 // 2) 
    rotation = cv.getRotationMatrix2D(center=center, angle=angle, scale=1.0)

    alpha = 1.5
    beta = 20

    while True:
        res, frame = cap.read()

        if not res:
            break
        
        frame = frame[roi_x:roi_x + roi_w, roi_y:roi_y+roi_h]
        cv.imshow('frame', frame)

        frame = cv.resize(frame, (105,105), interpolation=cv.INTER_AREA)
        
        rand = random.random()

        if rand <= 0.5:
            frame = cv.convertScaleAbs(frame, alpha=alpha, beta=beta)
        if rand <= 0.25:
            frame = cv.warpAffine(frame, rotation, (105,105))

        cv.imwrite(f"{AUTHED_DIR}/{uuid.uuid1()}.jpg", frame)
       
        if cv.waitKey(1) == ord('q'):
            break
    
    cap.release()
    cv.destroyAllWindows()


def clean_data_sets(raw_img_dir_path, clean_img_dir):

    counter = 0
    authed_dir_num = len(os.listdir(AUTHED_DIR)) - 1
    for image_name in os.listdir(raw_img_dir_path):

        if counter == authed_dir_num:
            break

        img = cv.imread(f"{raw_img_dir_path}/{image_name}")
        img = cv.resize(img, (105,105), interpolation=cv.INTER_AREA)

        cv.imwrite(f"{clean_img_dir}/{counter}.jpg", img)
        counter += 1


clean_data_sets(TRAIN_BAD_DIR, TRAIN_CLEAN_DIR)
clean_data_sets(VALID_BAD_DIR, VALID_CLEAN_DIR)