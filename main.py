import sys
import torch
import torchvision
from ultralytics import YOLO

from PyQt5.QtWidgets import QApplication
from app import App

def main():
    app = QApplication(sys.argv)  
    controller = App()           
    controller.run()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
