/* Add future slides as additional <section> elements inside .slides. */
Reveal.initialize({
  width: 1600,
  height: 900,
  margin: 0,
  minScale: 0.25,
  maxScale: 2,
  controls: false,
  progress: false,
  slideNumber: false,
  transition: 'none',
  backgroundTransition: 'none',
  center: false,
  hash: true,
});

// Keep the presentation clean when the demo file has not been added yet.
// Once videos/edgeglass-demo.mp4 exists, this swaps the placeholder for a native video player.
const demoVideo = document.querySelector('#edgeglass-demo');
const demoPlaceholder = document.querySelector('#demo-placeholder');

if (demoVideo && demoPlaceholder) {
  const videoPath = demoVideo.dataset.videoSrc;
  fetch(videoPath, { method: 'HEAD' })
    .then((response) => {
      if (!response.ok) return;
      demoVideo.querySelector('source').src = videoPath;
      demoVideo.hidden = false;
      demoPlaceholder.hidden = true;
      demoVideo.load();
    })
    .catch(() => {});
}
