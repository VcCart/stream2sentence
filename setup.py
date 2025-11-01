import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="stream2sentence", 
    version="0.3.2",
    author="VcCart",
    author_email="Vasya_Pupkin@web.com",
    description="Real-time processing and delivery of sentences from a continuous stream of characters or text chunks.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/VcCart/stream2sentence",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'stanza==v1.11.0'
    ],
    keywords='realtime, text streaming, stream, sentence, sentence detection, sentence generation, tts, speech synthesis, nltk, text analysis, audio processing, boundary detection, sentence boundary detection'
)
