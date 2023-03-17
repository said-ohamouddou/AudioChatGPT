from PyQt6.QtCore import (
    QUrl,
    QObject,
    pyqtSignal as Signal,
    pyqtSlot as Slot,
    Qt,
    QSize,
    QTimer,
    QDateTime,
    QThread)
from PyQt6.QtGui import QPainter, QPixmap, QFont, QMovie, QIcon
from PyQt6.QtWidgets import (
    QDialog, QStyle, QLineEdit, QPushButton, QTableWidget,
    QLabel, QVBoxLayout, QMessageBox, QWidget, QAbstractSlider,
    QApplication, QAbstractButton, QFrame, QMainWindow, QGroupBox,
    QScrollArea, QHBoxLayout, QSpacerItem, QSizePolicy, QSlider)
from qt_material import apply_stylesheet
from scipy.io.wavfile import write
from pydub import AudioSegment
from mutagen.mp3 import MP3
from time import sleep
from gtts import gTTS
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import threading
import queue
import langdetect
import sys
import os
import openai
import sys
import sounddevice
import soundfile
import pygame

MESSAGE_COUNT = 0
## Put your API key here
openai.api_key = 'API key here'
sounddevice.default.device = 2
pygame.mixer.init()

"""This class is to transform the audio into text and send it to chatgpt,
the response is transformed into audio and it displays it on the chat,
if the user's message is already in text, no transformation will be applied."""


class chatGPT(QObject):
    add_left_bubble = Signal(object)

    @Slot(object)
    def prepare_answer(self, request):
        try:
            global MESSAGE_COUNT
            if request['message_type'] == 'audio':
                audio_file = open(request['audio_filename'], 'rb')
                text_from_speech = openai.Audio.transcribe(
                    'whisper-1', audio_file)
                question_string = str(text_from_speech['text'])
            else:
                question_string = request['message_text']
            answer = openai.ChatCompletion.create(
                model='gpt-3.5-turbo', messages=[{'role': 'user', 'content': question_string}])
            answer_string = answer['choices'][0]['message']['content']
            if request['message_type'] == 'audio':
                lang = langdetect.detect(answer_string)
                answer_audio = gTTS(
                    text=answer_string.strip(
                        os.linesep), lang=lang, slow=False)
                answer_mp3_filename = Path(
                    'media/') / (str(MESSAGE_COUNT) + '_chatgpt_audio.mp3')
                answer_audio.save(answer_mp3_filename)
                answer_audio = AudioSegment.from_mp3(answer_mp3_filename)
                os.remove(answer_mp3_filename)
                answer_wav_filename = Path(
                    'media/') / (str(MESSAGE_COUNT) + '_chatgpt_audio.wav')
                answer_audio.export(answer_wav_filename, format='wav')
                request_answer = {
                    'message_type': 'audio',
                    'answer_filename': str(answer_wav_filename)}
                self.add_left_bubble.emit(request_answer)
                MESSAGE_COUNT += 1
            else:
                request_answer = {
                    'message_type': 'text',
                    'answer_text': answer_string}
                self.add_left_bubble.emit(request_answer)
        except BaseException:
            request_answer = {
                'message_type': 'text',
                'answer_text': 'Failed to connect to the ChatGPT,try later!'}
            self.add_left_bubble.emit(request_answer)


"""This class is to manage the sending of messages to chatgpt either in text or audio
format, the user can record an audio, cancel the recording and send text messages."""


class MessageSendingBar(QWidget):
    def __init__(self, parent=None):
        super(MessageSendingBar, self).__init__(parent)
        self.setFixedHeight(100)
        self.send_text_audio_layout = QHBoxLayout(self)
        self.text_message_input = QLineEdit()
        self.text_message_input.setPlaceholderText('Message')
        self.text_message_input.setFixedHeight(65)
        self.text_message_input.textChanged.connect(
            lambda: self.send_text_btn_ui())
        self.send_audio_btn = QPushButton()
        self.send_audio_btn.setIcon(QIcon(os.path.join('imgs', 'send.png')))
        self.send_audio_btn.setIconSize(QSize(45, 45))
        self.send_audio_btn.setStyleSheet('border:none')
        self.send_audio_btn.clicked.connect(lambda: self.send_audio())
        self.go_to_record_audio_btn = QPushButton()
        self.go_to_record_audio_btn.setIcon(
            QIcon(os.path.join('imgs', 'mic.png')))
        self.go_to_record_audio_btn.setIconSize(QSize(35, 35))
        self.go_to_record_audio_btn.setStyleSheet('border:none')
        self.go_to_record_audio_btn.clicked.connect(
            lambda: self.record_audio_ui())
        self.send_text_btn = QPushButton()
        self.send_text_btn.setStyleSheet('border: none;')
        self.send_text_btn.setIcon(QIcon(os.path.join('imgs', 'send.png')))
        self.send_text_btn.setIconSize(QSize(35, 35))
        self.send_text_btn.clicked.connect(lambda: self.send_text())
        self.cancel_record_btn = QPushButton()
        self.cancel_record_btn.setIcon(
            QIcon(os.path.join('imgs', 'cancel.png')))
        self.cancel_record_btn.clicked.connect(
            lambda: self.cancel_recording(True))
        self.send_text_audio_layout.addWidget(self.text_message_input)
        self.send_text_audio_layout.addWidget(self.go_to_record_audio_btn)
        self.recording_animation = QPushButton()
        self.recording_animation.setStyleSheet('border:none')
        self.audio_duration_label = QLabel('0:00')
        self.audio_duration_label.setStyleSheet(
            'color:white;font-weight: bold;font-size:20px;')
        self.audio_duration = QTimer()
        self.audio_duration.timeout.connect(self.show_audio_duration)
        self.recorded_seconds = 0
        self.recorded_minutes = 0
        self.cancel_record_btn_clicked = False
        self.audio_queue = queue.Queue()

    def record_audio_ui(self):
        self.audio_duration.start(1000)
        self.cancel_record_btn_clicked = False
        self.go_to_record_audio_btn.setParent(None)
        self.text_message_input.setEnabled(False)
        self.send_text_audio_layout.addWidget(self.recording_animation)
        self.send_text_audio_layout.addWidget(self.audio_duration_label)
        self.send_text_audio_layout.addWidget(self.cancel_record_btn)
        self.send_text_audio_layout.addWidget(self.send_audio_btn)
        self.start_record = threading.Thread(target=self.start_record_audio)
        self.start_record.start()

    def show_audio_duration(self):
        if self.recorded_seconds >= 60:
            self.recorded_seconds = 0
            self.recorded_minutes += 1
        self.audio_duration_label.setText(
            f'{self.recorded_minutes:01d}' + ':'
            f'{self.recorded_seconds:02d}   ')
        self.recorded_seconds += 1
        self.recording_animation.setIcon(
            QIcon(os.path.join('imgs', 'mic_red.png')))
        if (self.recorded_seconds % 2 == 0):
            self.recording_animation.setIcon(
                QIcon(os.path.join('imgs', 'mic.png')))
            self.recording_animation.setIconSize(QSize(25, 25))
        else:
            self.recording_animation.setIcon(
                QIcon(os.path.join('imgs', 'mic_red.png')))
            self.recording_animation.setIconSize(QSize(25, 25))
        if self.cancel_record_btn_clicked:
            self.recorded_seconds = 0
            self.recorded_minutes = 0

    def start_record_audio(self):
        global MESSAGE_COUNT
        device_info = sounddevice.query_devices('default', 'input')
        samplerate = int(device_info['default_samplerate'])
        self.request_audio_filename = Path('media/') / \
            (str(MESSAGE_COUNT) + '_user_audio.wav')
        with soundfile.SoundFile(self.request_audio_filename, mode='x', samplerate=samplerate,
                                 channels=1, subtype='PCM_24') as file:
            with sounddevice.InputStream(samplerate=samplerate, device='default',
                                         channels=1, callback=self.record_callback):
                while not self.cancel_record_btn_clicked:
                    file.write(self.audio_queue.get())
        MESSAGE_COUNT += 1

    def record_callback(self, indata, frames, time, status):
        self.audio_queue.put(indata.copy())

    def send_text_btn_ui(self):
        if (self.text_message_input.text() != ''):
            self.go_to_record_audio_btn.setParent(None)
            self.send_text_btn.setIcon(QIcon(os.path.join('imgs', 'send.png')))
            self.send_text_btn.setIconSize(QSize(35, 35))
            self.send_text_audio_layout.addWidget(self.send_text_btn)
        else:
            self.send_text_btn.setParent(None)
            self.send_text_audio_layout.addWidget(self.go_to_record_audio_btn)

    def send_text(self):
        global MESSAGE_COUNT
        pygame.mixer.music.load(os.path.join('sounds', 'sent.mp3'))
        app_home.chat_gpt_thread.start()
        app_home.message_bubbles_layout.addWidget(
            Bubble(
                self.text_message_input.text(),
                left=False,
                message_type='text'))
        MESSAGE_COUNT += 1
        pygame.mixer.music.play()
        self.buttom_spacer = QWidget()
        self.buttom_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding)
        if MESSAGE_COUNT == 1:
            app_home.message_bubbles_layout.addWidget(self.buttom_spacer)
        app_home.chat_gpt_thread.start()
        request = {'message_type': 'text',
                   'message_text': self.text_message_input.text()}
        app_home.send_user_request.emit(request)
        self.go_to_record_audio_btn.setEnabled(False)
        self.text_message_input.setText("")
        self.send_text_btn.setEnabled(False)

    def send_audio(self):
        self.cancel_recording()
        global MESSAGE_COUNT
        pygame.mixer.music.load(os.path.join('sounds', 'sent.mp3'))
        self.buttom_spacer = QWidget()
        self.buttom_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding)
        app_home.message_bubbles_layout.addWidget(
            Bubble(self.request_audio_filename, left=False))
        if MESSAGE_COUNT == 1:
            app_home.message_bubbles_layout.addWidget(self.buttom_spacer)
        pygame.mixer.music.play()
        app_home.chat_gpt_thread.start()
        request = {
            'message_type': 'audio',
            'audio_filename': str(self.request_audio_filename)}
        app_home.send_user_request.emit(request)
        self.go_to_record_audio_btn.setEnabled(False)
        self.send_text_btn.setEnabled(False)

    def cancel_recording(self, to_delete=False):
        global MESSAGE_COUNT
        self.cancel_record_btn_clicked = True
        if to_delete:
            os.remove(self.request_audio_filename)
            MESSAGE_COUNT -= 1
        self.text_message_input.setEnabled(True)
        self.recording_animation.setParent(None)
        self.cancel_record_btn.setParent(None)
        self.audio_duration_label.setParent(None)
        self.send_audio_btn.setParent(None)
        self.send_text_audio_layout.addWidget(self.go_to_record_audio_btn)


"""This class manages the graphical interface of the discussion, and allows to display
the messages sent by the user, read the audios sent, and the same thing for the reply messages."""


class Bubble(QWidget):
    def __init__(self, request, left=True, message_type='audio'):
        super(Bubble, self).__init__()
        current_date_and_time = datetime.now()
        bubble_layout = QHBoxLayout()
        bubble_layout_box = QHBoxLayout()
        if not left:
            bubble_layout_box.addSpacerItem(
                QSpacerItem(
                    1,
                    1,
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred))
        if message_type == 'audio':
            self.setFixedHeight(100)
            sleep(1)
            self.request_audio_filename = request
            audio = pygame.mixer.Sound(self.request_audio_filename)
            self.songLength = audio.get_length()
            self.audio_slider = QSlider(Qt.Orientation.Horizontal, self)
            self.audio_slider.setMaximum(round(self.songLength))
            self.play_pause_audio = QPushButton()
            self.play_pause_audio.clicked.connect(lambda: self.play_audio())
            self.audio_slider.sliderMoved.connect(
                lambda: self.play_pause_audio_from_second())
            self.audio_slider.sliderReleased.connect(
                lambda: self.audio_slider_released())
            play_icon = self.style().standardIcon(
                getattr(QStyle.StandardPixmap, 'SP_MediaPlay'))
            self.play_pause_audio.setIcon(play_icon)
            audio_duration = self.convert_to_minutes_and_seconds(
                self.songLength)
            bubble_groupbox = QGroupBox(
                audio_duration +
                ' at ' +
                current_date_and_time.strftime('%H:%M'))
            bubble_groupbox.setStyleSheet(
                'background-color: #31363b ;border: none;')
            bubble_groupbox.setLayout(bubble_layout)
            bubble_layout.addWidget(self.play_pause_audio)
            bubble_layout.addWidget(self.audio_slider)
        else:
            bubble_groupbox = QGroupBox(
                ' at ' + current_date_and_time.strftime('%H:%M'))
            bubble_groupbox.setStyleSheet(
                'background-color: #31363b ;border: none;')
            message, n_line = self.insert_new_lines(request)
            self.setFixedHeight(100 + (17 * (n_line - 1)))
            text_message_label = QLabel(message)
            text_message_label.setWordWrap(True)
            text_message_label.setStyleSheet(
                'color:white;font-weight: bold;font-size:13px;')
            bubble_layout.addWidget(text_message_label)
            bubble_groupbox.setLayout(bubble_layout)
        speaker_profil_img = QPushButton()
        speaker_profil_img.setEnabled(False)
        speaker_profil_img.resize(200, 64)
        speaker_profil_img.setStyleSheet('border: none;')
        if left:
            speaker_profil_img.setIcon(
                QIcon(os.path.join('imgs', 'chatgpt.png')))
            speaker_profil_img.setIconSize(QSize(50, 50))
        else:
            speaker_profil_img.setIcon(QIcon(os.path.join('imgs', 'user.png')))
            speaker_profil_img.setIconSize(QSize(30, 30))
        bubble_layout.addWidget(speaker_profil_img)
        bubble_layout_box.addWidget(bubble_groupbox)
        if left:
            bubble_layout_box.addSpacerItem(
                QSpacerItem(
                    1,
                    1,
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred))
        bubble_layout_box.setContentsMargins(0, 0, 0, 0)
        self.setLayout(bubble_layout_box)
        self.setContentsMargins(0, 0, 0, 0)
        self.first_play = True
        self.audio_slider_moving_by_user = False
        self.audio_is_played = False
        self.audio_is_paused = False
        self.audio_start_point = 0
        self.current_second = 0

    def play_audio(self):
        pygame.mixer.music.load(self.request_audio_filename)
        move_audio_slider_thread_1 = threading.Thread(
            target=self.audio_slider_moving)
        move_audio_slider_thread_2 = threading.Thread(
            target=self.audio_slider_moving)
        if not self.audio_is_played:
            pixmapi = getattr(QStyle.StandardPixmap, 'SP_MediaPause')
            icon = self.style().standardIcon(pixmapi)
            self.play_pause_audio.setIcon(icon)
            self.audio_is_played = True
            if self.first_play:
                self.first_play = False
                move_audio_slider_thread_1.start()
                pygame.mixer.music.play()

            else:
                pygame.mixer.music.unpause()
                self.audio_is_paused = False
                move_audio_slider_thread_2.start()

        else:
            self.audio_is_played = False
            self.audio_is_paused = True
            pixmapi = getattr(QStyle.StandardPixmap, 'SP_MediaPlay')
            icon = self.style().standardIcon(pixmapi)
            self.play_pause_audio.setIcon(icon)
            pygame.mixer.music.pause()

    def play_pause_audio_from_second(self):
        self.audio_slider_moving_by_user = True
        pygame.mixer.music.play(start=int(self.audio_slider.value()))
        pixmapi = getattr(QStyle.StandardPixmap, 'SP_MediaPause')
        icon = self.style().standardIcon(pixmapi)
        self.play_pause_audio.setIcon(icon)
        self.audio_is_played = True

    def audio_slider_released(self):
        self.audio_slider_moving_by_user = False
        self.current_second = self.audio_slider.value()

    def audio_slider_moving(self):
        for index in range(round(self.songLength) + 2):
            if not self.audio_slider_moving_by_user and self.audio_is_played:
                self.audio_slider.setValue(self.current_second)
                self.current_second = self.current_second + 1
                if round(self.songLength) + 2 == self.current_second:
                    self.first_play = True
                    pixmapi = getattr(QStyle.StandardPixmap, 'SP_MediaPlay')
                    icon = self.style().standardIcon(pixmapi)
                    self.play_pause_audio.setIcon(icon)
                    self.audio_slider.setValue(0)
                    self.current_second = 0
                    self.audio_is_played = False
            sleep(1)
            if self.audio_is_paused:
                return 0

    def convert_to_minutes_and_seconds(self, seconds):
        minutes = seconds // 60
        seconds %= 60
        return '%d:%02d' % (minutes, seconds)

    def insert_new_lines(self, text):
        words = text.split()
        lines = []
        current_line = ''
        for word in words:
            if len(word) > 55:
                for i in range(0, len(word), 55):
                    lines.append(word[i:i + 55])
                continue
            if len(current_line + word) > 55:
                lines.append(current_line.strip())
                current_line = ''
            current_line += word + ' '
        if current_line:
            lines.append(current_line.strip())
        return '\n'.join(lines), len(lines)


"""It is the main class of the application and allows to group all the components of the application."""


class Home(QMainWindow):
    send_user_request = Signal(object)

    def __init__(self, *args, **kwargs):
        super(Home, self).__init__(*args, **kwargs)
        app_name = 'AudiochatGPT'
        self.setWindowTitle(app_name)
        self.setFixedWidth(800)
        self.setFixedHeight(600)
        app_widget = QWidget()
        main_layout = QVBoxLayout(app_widget)
        app_header = QHBoxLayout()
        app_name_label = QLabel(app_name)
        app_name_label.setStyleSheet(
            'color:white;font-weight: bold;font-size:20px;')
        chatgpt_logo = QPushButton(app_name)
        chatgpt_logo.setIcon(QIcon(os.path.join('imgs', 'chatgpt.png')))
        chatgpt_logo.setIconSize(QSize(55, 55))
        chatgpt_logo.setStyleSheet('border: none;')
        app_header.addWidget(chatgpt_logo)
        right_spacer = QWidget()
        right_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed)
        app_header.addWidget(right_spacer)
        main_layout.addLayout(app_header)
        discussion_widget = QWidget()
        discussion_widget.setStyleSheet('background-color: #f0f3f7;')
        self.message_bubbles_layout = QVBoxLayout(discussion_widget)
        message_bubbles_layout_with_scroll = QVBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_to_bottom)
        self.scroll.setWidget(discussion_widget)
        self.scroll.setWidgetResizable(True)
        message_bubbles_layout_with_scroll.addWidget(self.scroll)
        main_layout.addLayout(message_bubbles_layout_with_scroll)
        self.message_sending_bar = MessageSendingBar()
        main_layout.addWidget(self.message_sending_bar)
        self.setCentralWidget(app_widget)
        self.chat_gpt_thread = QThread()
        self.chat_gpt = chatGPT()
        self.chat_gpt.add_left_bubble.connect(self.add_widget_from_thread)
        self.send_user_request.connect(self.chat_gpt.prepare_answer)
        self.chat_gpt.moveToThread(self.chat_gpt_thread)

    def add_widget_from_thread(self, request_answer):
        if self.message_sending_bar.buttom_spacer.parent() is not None:
            self.message_sending_bar.buttom_spacer.setParent(None)
        if request_answer['message_type'] == 'audio':
            self.message_bubbles_layout.addWidget(
                Bubble(request_answer['answer_filename']))
        else:
            self.message_bubbles_layout.addWidget(
                Bubble(request_answer['answer_text'], message_type='text'))
        pygame.mixer.music.load(os.path.join('sounds', 'incoming.mp3'))
        pygame.mixer.music.play()
        self.message_sending_bar.go_to_record_audio_btn.setEnabled(True)
        self.message_sending_bar.send_text_btn.setEnabled(True)

    def scroll_to_bottom(self):
        self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum())


if __name__ == '__main__':
    import sys
    AudioChatGPT = QApplication(sys.argv)
    apply_stylesheet(
        AudioChatGPT,
        theme=os.path.join(
            'style',
            'styleDark.xml'))
    app_home = Home()
    if os.path.exists('media'):
        shutil.rmtree('media')
    os.makedirs('media')
    app_home.show()
    AudioChatGPT.exec()
