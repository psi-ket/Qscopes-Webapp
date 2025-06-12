#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <LabJackM.h>
#include "LJM_Utilities.h" // ErrorCheck() etc.

void scan_voltages(int handle, double x_start, double y_start, double x_end, double y_end, int steps, double dwell_ms);

int main(int argc, char *argv[]) {
    // Default parameters
    double x_start = 0.3;
    double y_start = 0.3;
    double x_end = -0.3;
    double y_end = -0.3;
    int steps = 100;
    double dwell = 1; // milliseconds

    // Open LabJack
    int handle = OpenOrDie(LJM_dtT4, LJM_ctANY, "LJM_idANY");

    // Setup Counter (like Lua)
    LJM_eWriteName(handle, "DIO16_EF_ENABLE", 0);
    LJM_eWriteName(handle, "DIO16_EF_INDEX", 7);
    LJM_eWriteName(handle, "DIO16_EF_ENABLE", 1);

    // Start scanning
    scan_voltages(handle, x_start, y_start, x_end, y_end, steps, dwell);

    CloseOrDie(handle);
    return 0;
}

void scan_voltages(int handle, double x_start, double y_start, double x_end, double y_end, int steps, double dwell_ms) {
    if (steps < 2) {
        printf("Error: steps must be at least 2.\n");
        return;
    }

    const double MAX_VOLT = 5.0;
    const double MIN_VOLT = -5.0;
    double x_step = (x_end - x_start) / (steps - 1);
    double y_step = (y_end - y_start) / (steps - 1);

    double **matrix;
    int i, j;
    FILE *fp;

    // Allocate memory for matrix
    matrix = (double **)malloc(steps * sizeof(double *));
    for (i = 0; i < steps; i++) {
        matrix[i] = (double *)malloc(steps * sizeof(double));
    }

    printf("Starting 2D voltage scan...\n");

    for (i = 0; i < steps; i++) {
        double current_y = y_start + i * y_step;
        if (current_y > MAX_VOLT) current_y = MAX_VOLT;
        if (current_y < MIN_VOLT) current_y = MIN_VOLT;

        // Set Y voltage (DAC0)
        LJM_eWriteAddress(handle,30008,1, current_y);

        for (j = 0; j < steps; j++) {
            double current_x = x_start + j * x_step;
            if (current_x > MAX_VOLT) current_x = MAX_VOLT;
            if (current_x < MIN_VOLT) current_x = MIN_VOLT;

            // Set X voltage (DAC1)
            LJM_eWriteAddress(handle, 30010,1, current_y);
            double count = 0;
            // Dwell time
            LJM_eReadAddress(handle,3136,1, &count);
            struct timespec ts;
            ts.tv_sec = (time_t)(dwell_ms / 1000);
            ts.tv_nsec = (long)((dwell_ms - (ts.tv_sec * 1000)) * 1e6);
            nanosleep(&ts, NULL);
            // Read counter value
            LJM_eReadAddress(handle,3136,1, &count);
            // Save into matrix
            matrix[i][j] = count;
        }
    }

    printf("Scan complete. Saving matrix...\n");

    // Save the matrix to a text file
    fp = fopen("scan_matrix.txt", "w");
    if (fp == NULL) {
        perror("Failed to open file");
        return;
    }

    for (i = 0; i < steps; i++) {
        for (j = 0; j < steps; j++) {
            fprintf(fp, "%.0f ", matrix[i][j]); // No decimal places
        }
        fprintf(fp, "\n");
    }
    fclose(fp);

    printf("Matrix saved as 'scan_matrix.txt'\n");

    // Free memory
    for (i = 0; i < steps; i++) {
        free(matrix[i]);
    }
    free(matrix);

    // Reset voltages
    LJM_eWriteAddress(handle,30008,1, 0);
    LJM_eWriteAddress(handle,30010,1, 0);
}
