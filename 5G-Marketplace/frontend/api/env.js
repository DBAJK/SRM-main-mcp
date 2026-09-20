module.exports = (req, res) => {
  try {
    const key = process.env.GEMINI_API_KEY || '';
    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
    const safe = JSON.stringify(key);
    const script = `window.ENV=window.ENV||{};window.ENV.GEMINI_API_KEY=${safe};try{localStorage.setItem('geminiApiKey',${safe});}catch(e){}`;
    res.status(200).send(script);
  } catch (e) {
    res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
    res.status(200).send('window.ENV=window.ENV||{};');
  }
};
