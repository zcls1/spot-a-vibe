var constraints = {
    video:{facingMode: "user"},
    audio: false
};

 const cameraView = document.getElementById("camera--view");
 const cameraOutput = document.getElementById("camera--output");
 const cameraSensor = document.getElementById("camera--sensor");
 const cameraTrigger = document.getElementById("camera--capture");

 function cameraStart() {
    navigator.mediaDevices.getUserMedia(constraints)
    .then(function(stream) {
        track = stream.getTracks()[0];  
        cameraView.srcObject=stream;
    })
    .catch(function(error) {
        console.error("Oops. Something is broken.", error);
    });
}

cameraTrigger.onclick = function() {
    cameraSensor.width = cameraView.videoWidth;
    cameraSensor.height = cameraView.videoHeight;
    cameraSensor.getContext("2d").drawImage(cameraView, 0, 0);
    cameraOutput.src = cameraSensor.toDataURL("image/webp");
    cameraOutput.classList.add("taken");
}

window.addEventListener("load", cameraStart, false);