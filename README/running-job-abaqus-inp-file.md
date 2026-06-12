# Running a Job in Abaqus CAE

May 28, 2026

This document provides instructions for

- Uploading necessary documents for a complete job

- How to monitor the progress of a job

For instructions on how to visualize results, please see [Visualizing ODB Results Abaqus](visualizing-odb-results-abaqus.md)

Note: Not all models can be run on Bilbao. Higher computing power may be necessary in certain cases if your model will not populate.

## 1 Set Up

- Open Abaqus CAE

- Start a standard model

- As seen in figure 1, change the module to Job

<img src="assets/running-job-abaqus-inp-file/media/image1.png" style="width:5.3125in;height:3.17558in" />

Figure 1. Changing module to job

Once this has been done, select the following keys:

- Job

- Create...

<img src="assets/running-job-abaqus-inp-file/media/image2.png" style="width:4.81795in;height:3.83738in" />

Figure 2. Create new job

Now you are ready to upload your first file.

### 1.1 Model Design file

The first input file is the model’s structure and is saved as a .inp file. As seen in Figure 3, upload this .inp file by specifying the source as an input file. Then select your desired file from your documents.

<img src="assets/running-job-abaqus-inp-file/media/image3.png" style="width:1.90625in;height:2.67249in" />

Figure 3. Input job

<img src="assets/running-job-abaqus-inp-file/media/image4.png" style="width:4.92708in;height:3.21366in" />

Figure 4. Selecting input file

Now that the file is uploaded, we can change other parameters to properly run the job.

### 1.2 Source Code file

The .f file is necessary as it is the Fortran source code that will dictate the parameters underlying the model. Follow the following steps:

- General

- User subroutine file

- Locate your desired file

<img src="assets/running-job-abaqus-inp-file/media/image5.png" style="width:2.62173in;height:3.01282in" />

Figure 5. Change subroutine file

Nothing needs to be changed under the Memory or Parallelization tab. The Precision tab should be modified as seen in Figure 6.

- Abaqus/Explicit precision should be “Double - analysis + packager”

- Nodal output Precision should be “Full”

<img src="assets/running-job-abaqus-inp-file/media/image6.png" style="width:3.73958in;height:4.28165in" />

Figure 6. Modify the precision standards

You are now ready to submit the job.

## 2 Run the Job

### 2.1 Submitting the job

Follow these steps to submit the job:

- Job

- Submit

- Select your job name

<img src="assets/running-job-abaqus-inp-file/media/image7.png" style="width:4.02127in;height:4.60417in" />

Figure 7. Submit the job

### 2.2 Monitor Job

To monitor the job, follow these steps:

- Job

- Monitor

- Select your job name

- The progress of your job will propagate

<img src="assets/running-job-abaqus-inp-file/media/image8.png" style="width:3.63542in;height:3.24508in" />

Figure 8. Monitor the job

For more information on how to analyze the results, please see the document attached above.
