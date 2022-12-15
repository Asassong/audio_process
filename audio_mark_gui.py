import math
import sys
import os
from PyQt6.QtWidgets import QMainWindow, QFileDialog, QApplication, QGraphicsScene, QMessageBox
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl, Qt, QLineF
from PyQt6.QtGui import QPen, QColor
from window import Ui_MainWindow
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from asr import AsrDubObj


class MarkWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.gui = Ui_MainWindow()
        self.gui.setupUi(self)
        self.gui.choose.clicked.connect(self.ask_open_file)
        self.gui.output.clicked.connect(self.ask_save_file)
        self.gui.output_directory.editingFinished.connect(self.modify_output_path)
        self.gui.save_info.editingFinished.connect(self.modify_format_string)
        self.gui.source_file.activated[int].connect(self.process_now_file)  # 用str会报错
        self.audio = AudioSegment.empty()
        self.media_player = MediaPlayer()
        self.media_player.player.positionChanged.connect(self.get_now_play_time)
        self.gui.horizontalSlider.valueChanged.connect(self.change_now_time)
        self.gui.horizontalSlider.sliderReleased.connect(self.force_change_now_time)
        self.gui.save.clicked.connect(self.save_file)
        self.gui.add_start.clicked.connect(self.audio_add_start)
        self.gui.add_stop.clicked.connect(self.audio_add_stop)
        self.gui.add_split.clicked.connect(self.audio_add_split)
        self.gui.delete_last.clicked.connect(self.delete_last_point)
        self.gui.split_audio.clicked.connect(self.split_audio)
        self.gui.combine.clicked.connect(self.combine_audio)
        self.gui.f_asr.clicked.connect(self.asr_)
        self.line_object = []
        self.gui.play.clicked.connect(self.play_audio)
        self.gui.stop.clicked.connect(self.pause_audio)
        self.split_time = []
        self.source_file = []
        self.source_directory = ""
        self.output_path = ""
        self.output_format_string = "%06d.wav"
        self.save_file_name = 0
        self.audio_total_time = 0
        self.audio_now_time = 0
        self.canvas = FigureCanvasQTAgg()
        self.draw_scene = QGraphicsScene()
        self.gui.spectrum.setScene(self.draw_scene)
        self.gui.spectrum.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gui.spectrum.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gui.spectrum.show()

    def ask_open_file(self):
        self.source_directory = QFileDialog.getExistingDirectory(self, "选择音频所在文件夹", "./")
        self.gui.source_file.clear()
        self.source_file = os.listdir(self.source_directory)
        self.gui.source_file.addItems(self.source_file)
        self.gui.combine1.addItems(self.source_file)
        self.gui.combine2.addItems(self.source_file)
        self.process_now_file()

    def process_now_file(self):
        now_file = self.gui.source_file.currentText()
        if not self.output_format_string == "%s":
            self.gui.save_info.setText(self.output_format_string % self.save_file_name)
        self.gui.combine1.setCurrentText(now_file)
        self.gui.combine2.setCurrentText(now_file)
        self.audio = AudioSegment.from_wav(self.source_directory + "/" + now_file)
        self.audio_total_time = int(self.audio.duration_seconds * 1000 + 1)
        self.audio_now_time = 0
        self.line_object.clear()
        self.split_time.clear()
        self.gui.horizontalSlider.setSliderPosition(self.audio_now_time)
        self.gui.horizontalSlider.setRange(0, self.audio_total_time)
        self.gui.asr_result.setPlainText("")
        self.media_player.player.setSource(
            QUrl.fromLocalFile("%s/%s" % (self.source_directory, self.gui.source_file.currentText())))
        audio_data = np.frombuffer(self.audio._data, np.int16)
        matplotlib.use("Qt5Agg")
        fig = plt.figure(figsize=(6, 2))
        plt.xlim(0, len(audio_data))
        plt.subplots_adjust(top=1.0, left=0.0, right=1.0, bottom=0.0)
        plt.axis("off")
        plt.plot(audio_data)
        self.canvas = FigureCanvasQTAgg(fig)
        self.draw_scene.clear()
        self.draw_scene.addWidget(self.canvas)
        self.auto_split()

    def ask_save_file(self):
        self.output_path = QFileDialog.getExistingDirectory(self, "选择保存位置", "./")
        self.gui.output_directory.setText(self.output_path)
        self.flash_save_file()

    def flash_save_file(self):
        files = os.listdir(self.output_path)
        if len(files) > 0:
            if files[-1].replace(".wav", "").isdigit():
                self.save_file_name = int(files[-1].replace(".wav", "")) + 1
                if not self.output_format_string == "%s":
                    self.gui.save_info.setText(self.output_format_string % self.save_file_name)
                    if self.split_time:
                        self.flash_save_info()

    def modify_output_path(self):
        self.output_path = self.gui.output_directory.text()
        self.flash_save_file()

    def modify_format_string(self):
        output_file = self.gui.save_info.text()
        file_list = output_file.split(";")
        without_ext = file_list[-1].split(".")[0]
        if without_ext.isdigit():
            self.save_file_name = int(without_ext)
            if len(without_ext) >= len(str(self.save_file_name)):
                self.output_format_string = "%s0%dd.wav" % ("%", len(without_ext))
            else:
                self.output_format_string = "0d.wav"
        elif file_list[-1] == "":
            QMessageBox.about(self, "提示", "请不要输入多余的分号")
        else:
            self.output_format_string = "%s"

    def play_audio(self):
        self.media_player.player_state = True
        self.play()

    def pause_audio(self):
        self.media_player.player_state = False
        self.play()

    def play(self):
        self.media_player.player.setPosition(self.audio_now_time)
        if self.media_player.player_state:
            self.media_player.player.play()
        else:
            self.media_player.player.pause()

    def get_now_play_time(self, position):
        self.gui.horizontalSlider.setSliderPosition(position)

    def change_now_time(self, position):
        self.audio_now_time = position

    def force_change_now_time(self):
        self.audio_now_time = self.gui.horizontalSlider.value()

    def save_file(self, audio: AudioSegment = None, save_file_name=""):
        if self.output_path == "":
            self.message_output_not_set()
        if audio:
            audio.export(self.output_path + "/" + save_file_name, format="wav")
        else:
            file_name = self.gui.save_info.text()
            self.audio.export(self.output_path + "/" + file_name, format="wav")
            asr_result = self.gui.asr_result.toPlainText()
            if asr_result:
                with open(self.output_path + "/labels.txt", "a") as f:
                    f.write("%s|%s\n" % (file_name.replace(".wav", ""), asr_result))
            self.save_file_name += 1
            self.change_next_file()

    def change_next_file(self):
        index = self.gui.source_file.currentIndex()
        self.gui.source_file.removeItem(index)
        if self.gui.source_file.count() != 0:
            self.process_now_file()

    def message_output_not_set(self):
        self.pause_audio()
        QMessageBox.about(self, "提示", "保存文件路径未设置")

    def draw_line(self, position, color: QColor):
        now_position = self.gui.horizontalSlider.style().sliderPositionFromValue(5, self.audio_total_time,
                                                                                 position,
                                                                                 self.gui.horizontalSlider.width())
        line = QLineF(now_position, 0, now_position, self.gui.spectrum.height())
        self.line_object.append(self.draw_scene.addLine(line, QPen(color, 2)))

    def audio_add_start(self):
        now_value = self.gui.horizontalSlider.value()
        self.split_time.append(("start", now_value))
        self.draw_line(now_value, QColor(255, 0, 0))
        self.flash_save_info()

    def audio_add_stop(self):
        now_value = self.gui.horizontalSlider.value()
        self.split_time.append(("stop", now_value))
        self.draw_line(now_value, QColor(0, 0, 255))
        self.flash_save_info()

    def audio_add_split(self):
        now_value = self.gui.horizontalSlider.value()
        self.split_time.append(("split", self.gui.horizontalSlider.value()))
        self.draw_line(now_value, QColor(255, 0, 255))
        self.flash_save_info()

    def delete_last_point(self):
        if len(self.split_time) >= 1:
            self.split_time.pop(-1)
        if len(self.line_object) >= 1:
            self.draw_scene.removeItem(self.line_object[-1])
            self.line_object.pop(-1)
        self.flash_save_info()

    def flash_save_info(self):
        types = [i[0] for i in self.split_time]
        # 0  a  b      m 1
        #    a           1
        #       b        1
        #    a  c=ba     2
        #    b  c=a      2
        #       c=ba     2
        split_ = max(math.ceil((types.count("start") + types.count("stop"))/2), 1) + types.count("split")
        texts = []
        for i in range(split_):
            texts.append(self.output_format_string % (self.save_file_name + i))
        self.gui.save_info.setText(";".join(texts))

    def get_start_and_stop_time(self):
        start_and_stop_time = []
        sorted_time = sorted(self.split_time, key=lambda x: x[1])
        for type_, timestamp in sorted_time:
            if type_ == "start":
                start_and_stop_time.append([timestamp])
            elif type_ == "split":
                if start_and_stop_time:
                    if len(start_and_stop_time[-1]) == 1:
                        start_and_stop_time[-1].append(timestamp)
                    else:
                        start_and_stop_time.append([start_and_stop_time[-1][1], timestamp])
                else:
                    start_and_stop_time.append([0, timestamp])
                start_and_stop_time.append([timestamp])
            else:
                if start_and_stop_time:
                    start_and_stop_time[-1].append(timestamp)
                else:
                    start_and_stop_time.append([0, timestamp])
        if start_and_stop_time:
            if len(start_and_stop_time[-1]) == 1:
                start_and_stop_time[-1].append(self.audio_total_time-1)
        else:
            start_and_stop_time.append([0, self.audio_total_time-1])
        return start_and_stop_time

    def split_audio(self):
        start_and_stop_time = self.get_start_and_stop_time()
        file_names = self.gui.save_info.text().split(";")
        asr_result = self.gui.asr_result.toPlainText()
        if asr_result:
            results = asr_result.split(";")
        else:
            results = []
        i = 0
        for time_list in start_and_stop_time:
            if len(time_list) == 2:  # 分割加起点时只有一个
                audio = self.audio[time_list[0]: time_list[1]]
                self.save_file(audio, file_names[i])
                if results:
                    try:
                        with open(self.output_path + "/labels.txt", "a") as f:
                            f.write("%s|%s\n" % (file_names[i].replace(".wav", ""), results[i]))
                    except IndexError:
                        QMessageBox(self, "提示", "语音识别结果有误")
                i += 1
        file_name = file_names[-1].replace(".wav", "")
        if file_name.isdigit():
            num = int(file_name)
            self.save_file_name = num + 1
        self.change_next_file()

    def combine_audio(self):
        audio1 = AudioSegment.from_wav(self.source_directory + "/" + self.gui.combine1.currentText())
        audio2 = AudioSegment.from_wav(self.source_directory + "/" + self.gui.combine2.currentText())
        audio = audio1 + audio2
        self.save_file(audio, self.gui.save_info.text())
        self.save_file_name += 1
        self.change_next_file()

    def auto_split(self):
        chunks = detect_nonsilent(self.audio, 420, -40, 100)
        for start, stop in chunks:
            if stop - start > 1000:
                self.split_time.append(("start", start))
                self.draw_line(start, QColor(255, 0, 0))
                self.split_time.append(("stop", stop))
                self.draw_line(stop, QColor(0, 0, 255))
        self.flash_save_info()

    def asr_(self):
        asr = AsrDubObj()
        time_ = self.get_start_and_stop_time()
        result = []
        for start, stop in time_:
            result.append(asr(self.audio[start: stop], force_yes=True))
        self.gui.asr_result.setPlainText(";".join(result))


class MediaPlayer:
    def __init__(self):
        self.player = QMediaPlayer()
        self.audioOutput = QAudioOutput()
        self.player.setAudioOutput(self.audioOutput)
        self.player_state = False
        self.voice = 0.5
        self.audioOutput.setVolume(self.voice)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MarkWindow()
    window.show()
    sys.exit(app.exec())
