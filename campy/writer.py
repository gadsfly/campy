"""
"""
from imageio_ffmpeg import write_frames
import os, sys, time, logging
import psutil
from campy.cameras import unicam
from campy.utils.utils import QueueKeyboardInterrupt

def OpenWriter(cam_params, queue):
    try:
        # p = psutil.Process(os.getpid())
        # p.nice(psutil.HIGH_PRIORITY_CLASS)#psutil.REALTIME_PRIORITY_CLASS note real-time takes precidence over operating system and can cause the computer to crash if buffers are not being flushed p.nice(psutil.REALTIME_PRIORITY_CLASS)
        writing = False
        folder_name = os.path.join(cam_params["videoFolder"], cam_params["cameraName"])
        file_name = cam_params["videoFilename"]
        full_file_name = os.path.join(folder_name, file_name)

        if not os.path.isdir(folder_name):
            os.makedirs(folder_name)
            print("Made directory {}.".format(folder_name))

        # Flip blue and red for flir camera input
        if cam_params["pixelFormatInput"] == "bayer_bggr8" and cam_params["cameraMake"] == "flir":
            cam_params["pixelFormatInput"] == "bayer_rggb8"

        # Load encoding parameters from cam_params
        pix_fmt_out = cam_params["pixelFormatOutput"]
        codec = str(cam_params["codec"])
        quality = str(cam_params["quality"])
        preset = str(cam_params["preset"])
        frameRate = str(cam_params["frameRate"])
        gpuID = str(cam_params["gpuID"])

        # Load defaults
        gpu_params = []

        # CPU compression
        if cam_params["gpuID"] == -1:
            print("Opened: {} using CPU to compress the stream.".format(full_file_name))
            if preset == "None":
                preset = "fast"
            gpu_params = ["-r:v", frameRate,
                        "-preset", preset,
                        "-tune", "fastdecode",
                        "-crf", quality,
                        "-bufsize", "20M",
                        "-maxrate", "10M",
                        "-bf:v", "4",
                        "-vsync", "0",]
            if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
                pix_fmt_out = "yuv420p"
            if cam_params["codec"] == "h264":
                codec = "libx264"
                gpu_params.append("-x264-params")
                gpu_params.append("nal-hrd=cbr")
            elif cam_params["codec"] == "h265":
                codec = "libx265"

        # GPU compression
        else:
            # Nvidia GPU (NVENC) encoder optimized parameters
            print("Opened: {} using GPU {} to compress the stream.".format(full_file_name, cam_params["gpuID"]))
            if cam_params["gpuMake"] == "nvidia" and (cam_params["rateControl"] == "0" or cam_params["rateControl"] == "2" or cam_params["rateControl"] == "16"):
                if preset == "None":
                    preset = "fast"
                gpu_params = ["-r:v", frameRate, # important to play nice with vsync "0"
                            "-preset", preset, # set to "fast", "llhp", or "llhq" for h264 or hevc
                            "-qp", quality,
                            "-bf:v", "0",
                            "-vsync", "0",
                            "-2pass", "0",
                            "-gpu", gpuID,
                            ]
                if cam_params["codec"] == "h264":
                    codec = "h264_nvenc"
                elif cam_params["codec"] == "h265":
                    codec = "hevc_nvenc"
            
            if cam_params["gpuMake"] == "nvidia" and (cam_params["rateControl"] == "1" or cam_params["rateControl"] == "32"):
                if preset == "None":
                    preset = "fast"
                gpu_params = ["-preset", preset, # set to "fast", "llhp", or "llhq" for h264 or hevc
                            # "-r:v", "10", #frameRate, # important to play nice with vsync "0"
                            # "-qp", quality,
                            # "-bf:v", "0",
                            # "-vsync", "0",
                            '-rc', cam_params["rateControl"], # variable bit rate - 32 for high quality, 1 for normal
                            '-2pass', '1',    # sets two pass encoding to true, slightly slower but gives a much more consistent compression
                            '-rc-lookahead', '1536', #'1664', # #important for temporal-aq and 2-pass encoding. Allows for a larger number of frames to look at changes over time and where to assign complexity (complexity roughly equates to video size)
                            '-temporal-aq', '1', #can either use temporal-aq or spatial-aq not both. Temporal is better since the frame as a whole changes very little over time. Temporal also uses cuda and 3D cores on gpu
                            '-surfaces', '64', #greatly affects temporal-aq can never get this setting perfect with rc-lookahead but ffmpeg adjusts it automatically so it doesn't matter
                            '-b:v', cam_params["avgBitRate"] , #the average bitrate, this is what controls are video size
                            '-maxrate', cam_params["maxBitRate"] , #the max bitrate, this controls the upper bounds of our video size for a section of frames
                            '-minrate:v', '500000', #the min bitrate, this controls the lower bounds of our video size for a section of frames
                            '-bufsize', cam_params["gpuBuffer"], #The buffer is important for stabalizing video write and read spead
                            '-threads', '16', # we don't need many since we are using gpu encoding, however we need one to handle the stream to the gpu and one or two to handle the -rc-lookahead
                            # '-pix_fmt', 'yuv420p', #specifies our pixel format. Nvidia doesn't allow for greyscale encoding so we have to encode the video as three colors
                            "-gpu", gpuID,
                            ]
                if cam_params["codec"] == "h264":
                    codec = "h264_nvenc"
                elif cam_params["codec"] == "h265":
                    codec = "hevc_nvenc"

            # AMD GPU (AMF/VCE) encoder optimized parameters
            elif cam_params["gpuMake"] == "amd":
                # Preset not supported by AMF
                gpu_params = ["-r:v", frameRate,
                            "-usage", "lowlatency",
                            "-rc", "cqp", # constant quantization parameter
                            "-qp_i", quality,
                            "-qp_p", quality,
                            "-qp_b", quality,
                            "-bf:v", "0",
                            "-hwaccel", "auto",
                            "-hwaccel_device", gpuID,]
                if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
                    pix_fmt_out = "yuv420p"
                if cam_params["codec"] == "h264":
                    codec = "h264_amf"
                elif cam_params["codec"] == "h265":
                    codec = "hevc_amf"

            # Intel iGPU encoder (Quick Sync) optimized parameters				
            elif cam_params["gpuMake"] == "intel":
                if preset == "None":
                    preset = "faster"
                gpu_params = ["-r:v", frameRate,
                            "-bf:v", "0",
                            "-preset", preset,
                            "-q", str(int(quality)+1),]
                if pix_fmt_out == "rgb0" or pix_fmt_out == "bgr0":
                    pix_fmt_out = "nv12"
                if cam_params["codec"] == "h264":
                    codec = "h264_qsv"
                elif cam_params["codec"] == "h265":
                    codec = "hevc_qsv"

    except Exception as e:
        logging.error("Caught exception at writer.py OpenWriter: {}".format(e))
        raise

    # Initialize writer object (imageio-ffmpeg)
    while(True):
        try:
            writer = write_frames(
                full_file_name,
                [cam_params["frameWidth"], cam_params["frameHeight"]], # size [W,H]
                fps=cam_params["frameRate"],
                quality=None,
                codec=codec,
                pix_fmt_in=cam_params["pixelFormatInput"], # "bayer_bggr8", "gray", "rgb24", "bgr0", "yuv420p"
                pix_fmt_out=pix_fmt_out,
                bitrate=None,
                ffmpeg_log_level=cam_params["ffmpegLogLevel"], # "warning", "quiet", "info"
                input_params=["-an"], # "-an" no audio
                output_params=gpu_params,
                )
            writer.send(None) # Initialize the generator
            writing = True
            break
            
        except Exception as e:
            logging.error("Caught exception at writer.py OpenWriter: {}".format(e))
            raise
            break

    # Initialize read queue object to signal interrupt
    readQueue = {}
    readQueue["queue"] = queue
    readQueue["message"] = "STOP"

    return writer, writing, readQueue

def AuxWriteFrames(cam_params, writeQueue, stopReadQueue, stopWriteQueue):
	# Start ffmpeg video writer 
	writer, writing, readQueue = OpenWriter(cam_params, stopReadQueue)

	
	while(writing):
		if writeQueue:
			print(len(writeQueue))
			if len(writeQueue) > 0: 
				writer.send(writeQueue.popleft())
		else:
			# Once queue is depleted and grabber stops, then stop writing
			if stopWriteQueue:
				writing = False
			# Otherwise continue writing
			time.sleep(0.01)

	# Close up...
	print("Closing video writer for {}. Please wait...".format(cam_params["cameraName"]))
	time.sleep(1)
	writer.close()
 
def AuxWriteFramesMainThread(cam_params, writeQueue, stopReadQueue, stopWriteQueue):
	# Start ffmpeg video writer 
	writer, writing, readQueue = OpenWriter(cam_params, stopReadQueue)

	with QueueKeyboardInterrupt(readQueue):
		# Write until interrupted and/or stop message received
		while(writing):
			if writeQueue:
				print(len(writeQueue))
				if len(writeQueue) > 0:
					writer.send(writeQueue.popleft())
			else:
				# Once queue is depleted and grabber stops, then stop writing
				if stopWriteQueue:
					writing = False
				# Otherwise continue writing
				time.sleep(0.01)

	# Close up...
	print("Closing video writer for {}. Please wait...".format(cam_params["cameraName"]))
	time.sleep(1)
	writer.close()

def WriteFrames(cam_params, writeQueue, stopReadQueue, stopWriteQueue):
    # Start ffmpeg video writer 
    writer, writing, readQueue = OpenWriter(cam_params, stopReadQueue)
    cam = unicam.ImportCam(cam_params["cameraMake"])
    t = time.time()
    cc = 0
    with QueueKeyboardInterrupt(readQueue):
        # Write until interrupted and/or stop message received
        while(writing):
            
            if writeQueue:
                
                if cam_params["printWriteQueue"] and len(writeQueue) > cam_params["printWriteQueue"] :
                    print(cam_params["cameraName"] + " -> " + str(len(writeQueue)))
                # print(time.time() - t)
                # writeQueue.popleft()
                # cc = cc+1
                # if cc > 1000:
                #     print("Post-pop: ", time.time() - t)
                #     t = time.time()
                #     cc = 0
                # writer.send(cam.GetImageArray(writeQueue.popleft()))
                writer.send(writeQueue.popleft())
                
            else:
                # Once queue is depleted and grabber stops, then stop writing
                if stopWriteQueue:
                    writing = False
                # Otherwise continue writing
                time.sleep(0.01)

    # Close up...
    print("Closing video writer for {}. Please wait...".format(cam_params["cameraName"]))
    time.sleep(1)
    writer.close()
    

