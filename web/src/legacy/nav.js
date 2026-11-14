// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
// The ported modules navigate through these three functions; the Chrome component hooks them to the Next router.
// Filters of a catalogue change the address without a server round trip (Next syncs history.pushState/replaceState).
let router = null;
export const setRouter = r => { router = r; };
export const go = (url, { replace = false } = {}) => {
  if (router) (replace ? router.replace(url) : router.push(url));
  else location.assign(url);
};
export const replaceUrl = url => history.replaceState(history.state, '', url);
export const pushUrl = url => history.pushState(history.state, '', url);
