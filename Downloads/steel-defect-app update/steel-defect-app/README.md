# Steel Defect Detection App

## Backend
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload      # http://127.0.0.1:8000/docs

## Frontend
    cd frontend
    npm install
    npm run dev                    # http://localhost:5173

## YOLO + SAM2
Copy your trained YOLO weights to `backend/models/yolo_best.pt` (without it the app runs classifier + Grad-CAM only).
SAM2 (`sam2.1_t.pt`) is downloaded automatically by ultralytics on first run.
