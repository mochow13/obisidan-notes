Based on [Understanding Multimodal LLMs](https://magazine.sebastianraschka.com/p/understanding-multimodal-llms?hide_intro_popup=true)
## What are multimodal LLMs?

> *Multimodal LLMs are large language models capable of processing multiple types of inputs, where each "modality" refers to a specific type of data—such as text (like in traditional LLMs), sound, images, videos, and more.*

A common use case is image captioning—provide an image and the model generates a description of the image.
## Architecture of multimodal LLMs

There are two common approaches:
- Unified embedding decoder architecture
- Cross-modality attention architecture

### Unified embedding decoder architecture

In this architecture, just like text decoder LLMs, images are converted into embedding vectors. For text, a tokenizer and an embedding layer are used to generate the embeddings. Similar to that, an image encoder modules is used to generate embeddings for the images.

![](https://substackcdn.com/image/fetch/$s_!_DNf!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ffef5f8cb-c76c-4c97-9771-7fdb87d7d8cd_1600x1135.png)

From the diagram above, we can notice—
- Images are chunked into smaller patches
- The patches are forwarded through *linear projection* and *transformer encoder*
- Transformer encoder is a vision transformer model (ViT)
	- Example: https://github.com/openai/CLIP
- ViT is a pre-trained model that encodes the images

The linear projection layer projects the image chunks to an embedding size compatible with the transformer encoder. In the diagram below, image patch vector with dimension 256 is projected to 768. 

![](https://substackcdn.com/image/fetch/$s_!i9i4!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fee32d720-92d7-48c2-b39d-adf61a870075_1600x681.png)

There can also be another projector layer after the vision transformer layer as shown in the following diagram.

![](https://substackcdn.com/image/fetch/$s_!TaTW!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5d0be64c-da90-4193-86db-804f6a8a0abb_1542x1242.png)

So we finally get image patches projected to embedding dimensions that match the text embedding dimension. The result is, we can now simply concatenate the image and text embeddings and give it as input to the LLM.

![](https://substackcdn.com/image/fetch/$s_!FTft!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fa219f185-211b-4569-9398-2e080e2c5619_1166x1400.png)
### Cross-modality attention architecture

In this architecture, image patches are added to the transformer not as an input to the LLM, rather as an input to the multi-headed attention layer.

![](https://substackcdn.com/image/fetch/$s_!7Xvv!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd9c06055-b959-45d1-87b2-1f4e90ceaf2d_1296x1338.png)

This is similar to the encoder-decoder architecture of the original transformer paper.

![](https://substackcdn.com/image/fetch/$s_!JYyE!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5d028b95-7965-43e0-b8fc-350609a69377_1370x1582.png)

#### What is Cross-Attention?

![](https://substackcdn.com/image/fetch/$s_!3PZD!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ffe4cc6f4-ca9a-431b-b572-95a1fda373a7_1508x1120.png)

In cross attention, there are two different inputs as shown in the diagram—$x_1$ and $x_2$. They can have different number of tokens $n$ and $m$. But their embedding dimension has to be the same.

