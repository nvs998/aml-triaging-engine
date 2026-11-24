# Tech-band logos

The scrolling technology band in `docs/index.html` loads a logo for each item from this folder.
Until a file is present, the page shows a generic icon plus the name, so nothing breaks.

Download each logo from the vendor's official brand or press page, preferably the white or
"for dark backgrounds" version (the band is dark navy), save it here as SVG with these names,
and check each vendor's brand guidelines for how the logo may be used:

python.svg · uv.svg · fastapi.svg · pydantic.svg · crewai.svg · gemini.svg ·
iso20022.svg · companies-house.svg · websockets.svg · sqlite.svg · httpx.svg · faker.svg ·
docker.svg · azure.svg

If a file is a full wordmark (logo already contains the name), add `wordmark` to that
`<img class="logo">` in `docs/index.html` so the text label is hidden and not shown twice.
(Each item appears twice in the markup because the band loops; update both.)
