import cv2 as cv
import numpy as np
import glob
import os
from pupil_apriltags import Detector
from ultralytics import YOLO

TAG_SIZE_METERS = 0.05
# Modelo treinado por você (6 classes: argola_grande, argola_pequena, cilindro_com_base,
# dado_hexagonal, helice, paraboloide_hiperbolico). Coloque o arquivo na mesma pasta do script
# ou ajuste o caminho abaixo.
YOLO_MODEL = "weights_model.pt"
YOLO_CONF = 0.6   # limiar de confiança; reduza (ex.: 0.4) se o modelo treinado detectar pouco
CHESSBOARD_SIZE = (8, 5)

def calibrate_camera():
    #Realiza a calibração da câmera usando as imagens de xadrez na pasta
    print("[INFO] Iniciando calibração da câmera...")
    criteria = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    
    objp = np.zeros((CHESSBOARD_SIZE[0] * CHESSBOARD_SIZE[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHESSBOARD_SIZE[0], 0:CHESSBOARD_SIZE[1]].T.reshape(-1, 2)
    
    objpoints = [] # Pontos 3D no mundo real
    imgpoints = [] # Pontos 2D no plano da imagem
    
    images = glob.glob('*.jpg')
    if not images:
        print("[ERRO] Nenhuma imagem .jpg encontrada para calibração!")
        exit()
        
    for fname in images:
        img = cv.imread(fname)
        gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        ret, corners = cv.findChessboardCorners(gray, CHESSBOARD_SIZE, None)
        
        if ret:
            objpoints.append(objp)
            corners2 = cv.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)

            cv.drawChessboardCorners(img, (8,5), corners2, ret)
            cv.imshow('img', img)
            cv.waitKey(100)
            
    print("[INFO] Calculando matriz da câmera...")
    ret, mtx, dist, rvecs, tvecs = cv.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
    print("[INFO] Calibração concluída com sucesso!\n")
    return mtx, dist

def main():
    mtx, dist = calibrate_camera()
    
    # Extrair os parâmetros da câmera da matriz (fx, fy, cx, cy)
    fx, fy = mtx[0, 0], mtx[1, 1]
    cx, cy = mtx[0, 2], mtx[1, 2]
    camera_params = (fx, fy, cx, cy)

    print("[INFO] Carregando YOLO e AprilTag...")
    model_path = YOLO_MODEL if os.path.isabs(YOLO_MODEL) else os.path.join(os.path.dirname(os.path.abspath(__file__)), YOLO_MODEL)
    if not os.path.isfile(model_path):
        print(f"[ERRO] Modelo YOLO não encontrado: {model_path}")
        exit()
    yolo_model = YOLO(model_path)
    print(f"[INFO] Modelo carregado. Classes: {yolo_model.names}")
    
    at_detector = Detector(
        families="tag25h9",
        nthreads=1,
        quad_decimate=1.0,
        quad_sigma=0.0,
        refine_edges=1,
        decode_sharpening=0.25,
        debug=0
    )

    # 3. Iniciar Webcam
    cap = cv.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Remover distorção da lente (opcional, mas recomendado para medições precisas)
        frame = cv.undistort(frame, mtx, dist, None, mtx)
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)

        # -- A. Detectar AprilTag (com estimativa de pose 3D) --
        tags = at_detector.detect(gray, estimate_tag_pose=True, camera_params=camera_params, tag_size=TAG_SIZE_METERS)
        
        for tag in tags:
            # tag.pose_t é um vetor [X, Y, Z] de translação da tag em relação à câmera
            tag_pose_3d = tag.pose_t.flatten() 
            tag_z = tag_pose_3d[2] # Profundidade (Z)
            
            # Centro da Tag na imagem (pixels)
            tag_center_2d = (int(tag.center[0]), int(tag.center[1]))
            
            # Desenhar contorno e centro da Tag
            cv.circle(frame, tag_center_2d, 5, (0, 0, 255), -1)
            cv.putText(frame, f"Tag Z: {tag_z:.2f}m", (tag_center_2d[0]-20, tag_center_2d[1]-20), 
                        cv.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        results = yolo_model.predict(frame, conf=YOLO_CONF, verbose=False)
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                # Coordenadas do Bounding Box
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls = int(box.cls[0].cpu().numpy())
                nome_classe = yolo_model.names[cls]
                
                # Calcular o centro do objeto detectado pelo YOLO (em pixels)
                obj_center_u = (x1 + x2) / 2.0
                obj_center_v = (y1 + y2) / 2.0
                obj_center_2d = (int(obj_center_u), int(obj_center_v))
                
                # Desenhar Bounding box e centro
                cv.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv.circle(frame, obj_center_2d, 5, (0, 255, 0), -1)
                
                # Nome da classe detectada (sem cálculo de distância até a Tag)
                cv.putText(frame, nome_classe, (int(x1), int(y1)-10),
                            cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv.imshow("Webcam - Distancia Tag-YOLO", frame)

        if cv.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv.destroyAllWindows()

if __name__ == "__main__":
    main()