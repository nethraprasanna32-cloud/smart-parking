from ultralytics import YOLO
import cv2

# Load YOLO11 nano model
model = YOLO("yolo11n.pt")

# Open Mac webcam
cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()

    if not ret:
        print("Could not read camera")
        break

    # Run YOLO detection
    results = model(frame)

    # Draw bounding boxes
    annotated_frame = results[0].plot()

    # Display
    cv2.imshow("Smart Parking - Vehicle Detection", annotated_frame)

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()