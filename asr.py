import os
import sys
import paddle
import time
from paddlespeech.cli.utils import stats_wrapper, CLI_TIMER
from paddlespeech.audio.transform.transformation import Transformation
from paddlespeech.cli.asr.infer import ASRExecutor
import numpy as np
from pydub import AudioSegment
from paddlespeech.cli.log import logger
import librosa

__all__ = ['ASRExecutor']


class AsrDubObj(ASRExecutor):
    def __init__(self):
        super().__init__()
        self.pydub_audio = AudioSegment.empty()
        self.pydub_sample_rate = 44100

    def _check(self, audio_file: AudioSegment, sample_rate: int, force_yes: bool = False):
        self.sample_rate = sample_rate
        if self.sample_rate != 16000 and self.sample_rate != 8000:
            logger.error(
                "invalid sample rate, please input --sr 8000 or --sr 16000")
            return False
        logger.debug("checking the audio file format......")
        try:
            # audio, audio_sample_rate = soundfile.read(
            #     audio_file, dtype="int16", always_2d=True)
            audio_sample_rate = self.pydub_sample_rate
            audio = self.pydub_audio
            audio_duration = audio.shape[0] / audio_sample_rate
            if audio_duration > self.max_len:
                logger.error(
                    f"Please input audio file less then {self.max_len} seconds.\n"
                )
                return False
        except Exception as e:
            logger.exception(e)
            logger.error(
                f"can not open the audio file, please check the audio file({audio_file}) format is 'wav'. \n \
                 you can try to use sox to change the file format.\n \
                 For example: \n \
                 sample rate: 16k \n \
                 sox input_audio.xx --rate 16k --bits 16 --channels 1 output_audio.wav \n \
                 sample rate: 8k \n \
                 sox input_audio.xx --rate 8k --bits 16 --channels 1 output_audio.wav \n \
                 ")
            return False
        logger.debug("The sample rate is %d" % audio_sample_rate)
        if audio_sample_rate != self.sample_rate:
            logger.warning("The sample rate of the input file is not {}.\n \
                            The program will resample the wav file to {}.\n \
                            If the result does not meet your expectations，\n \
                            Please input the 16k 16 bit 1 channel wav file. \
                        ".format(self.sample_rate, self.sample_rate))
            if force_yes is False:
                while True:
                    logger.debug(
                        "Whether to change the sample rate and the channel. Y: change the sample. N: exit the prgream."
                    )
                    content = input("Input(Y/N):")
                    if content.strip() == "Y" or content.strip(
                    ) == "y" or content.strip() == "yes" or content.strip(
                    ) == "Yes":
                        logger.debug(
                            "change the sampele rate, channel to 16k and 1 channel"
                        )
                        break
                    elif content.strip() == "N" or content.strip(
                    ) == "n" or content.strip() == "no" or content.strip(
                    ) == "No":
                        logger.debug("Exit the program")
                        return False
                    else:
                        logger.warning("Not regular input, please input again")

            self.change_format = True
        else:
            logger.debug("The audio file format is right")
            self.change_format = False

        return True

    def preprocess(self, model_type: str, input: AudioSegment):
        """
        Input preprocess and return paddle.Tensor stored in self.input.
        Input content can be a text(tts), a file(asr, cls) or a streaming(not supported yet).
        """

        audio_file = input
        # Get the object for feature extraction
        if "deepspeech2" in model_type or "conformer" in model_type or "transformer" in model_type:
            logger.debug("get the preprocess conf")
            preprocess_conf = self.config.preprocess_config
            preprocess_args = {"train": False}
            preprocessing = Transformation(preprocess_conf)
            logger.debug("read the audio file")
            audio_sample_rate = self.pydub_sample_rate
            audio = self.pydub_audio
            if self.change_format:
                # if audio.shape[1] >= 2:
                #     audio = audio.mean(axis=1, dtype=np.int16)
                # else:
                #     audio = audio[:, 0]
                # pcm16 -> pcm 32
                audio = self._pcm16to32(audio)
                audio = librosa.resample(
                    audio,
                    orig_sr=audio_sample_rate,
                    target_sr=self.sample_rate)
                audio_sample_rate = self.sample_rate
                # pcm32 -> pcm 16
                audio = self._pcm32to16(audio)
            else:
                audio = audio[:, 0]

            logger.debug(f"audio shape: {audio.shape}")
            # fbank
            audio = preprocessing(audio, **preprocess_args)

            audio_len = paddle.to_tensor(audio.shape[0])
            audio = paddle.to_tensor(audio, dtype='float32').unsqueeze(axis=0)

            self._inputs["audio"] = audio
            self._inputs["audio_len"] = audio_len
            logger.debug(f"audio feat shape: {audio.shape}")

        else:
            raise Exception("wrong type")

        logger.debug("audio feat process success")

    @stats_wrapper
    def __call__(self,
                 audio_file: AudioSegment,
                 model: str = 'conformer_wenetspeech',
                 lang: str = 'zh',
                 sample_rate: int = 16000,
                 config: os.PathLike = None,
                 ckpt_path: os.PathLike = None,
                 decode_method: str = 'attention_rescoring',
                 num_decoding_left_chunks: int = -1,
                 force_yes: bool = False,
                 rtf: bool = False,
                 device=paddle.get_device()):
        """
        Python API to call an executor.
        """
        # audio_file = os.path.abspath(audio_file)
        paddle.set_device(device)
        self._init_from_path(model, lang, sample_rate, config, decode_method,
                             num_decoding_left_chunks, ckpt_path)
        audio_array = audio_file.get_array_of_samples()
        self.pydub_sample_rate = audio_file.frame_rate
        self.pydub_audio = np.array(audio_array, dtype=np.int16)
        if not self._check(audio_file, sample_rate, force_yes):
            sys.exit(-1)
        if rtf:
            k = self.__class__.__name__
            CLI_TIMER[k]['start'].append(time.time())

        self.preprocess(model, audio_file)
        self.infer(model)
        res = self.postprocess()  # Retrieve result of asr.

        if rtf:
            CLI_TIMER[k]['end'].append(time.time())
            # audio, audio_sample_rate = soundfile.read(
            #     audio_file, dtype="int16", always_2d=True)
            CLI_TIMER[k]['extra'].append(audio_array.shape[0] / self.pydub_sample_rate)

        return res
