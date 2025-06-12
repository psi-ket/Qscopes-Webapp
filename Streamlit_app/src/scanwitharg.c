#include <stdbool.h>
#ifdef _WIN32
    #include <winsock2.h>
    #include<windows.h>
    #include <ws2tcpip.h>
#else
    #include <arpa/inet.h>  // For inet_ntoa()
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>  // Include time functions

#include <LabJackM.h>
#include "LJM_Utilities.h"

void ReadLuaInfo(int handle);

int main(int argc, char *argv[])
{
    // Set default values
    double x_start = 0.5;
    double y_start = 0.5;
    double x_end = -0.5;
    double y_end = -0.5;
    int steps = 50;
    double dwell = 2.0;

    // Parse command line arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-xs") == 0 && i + 1 < argc) {
            x_start = atof(argv[++i]);
        }
        else if (strcmp(argv[i], "-ys") == 0 && i + 1 < argc) {
            y_start = atof(argv[++i]);
        }
        else if (strcmp(argv[i], "-xe") == 0 && i + 1 < argc) {
            x_end = atof(argv[++i]);
        }
        else if (strcmp(argv[i], "-ye") == 0 && i + 1 < argc) {
            y_end = atof(argv[++i]);
        }
        else if (strcmp(argv[i], "-st") == 0 && i + 1 < argc) {
            steps = atoi(argv[++i]);
        }
        else if (strcmp(argv[i], "-dw") == 0 && i + 1 < argc) {
            dwell = atof(argv[++i]);
        }
        else {
            fprintf(stderr, "Unknown option or missing argument: %s\n", argv[i]);
            return 1;
        }
    }
    int err;
    double numBytes;
    char *aBytes;
    int errorAddress;
    int handle;
    
    handle = OpenOrDie(LJM_dtT7, LJM_ctANY, "LJM_idANY");
    // LJM_eWriteAddress(handle,61998,1,1279918080);
    // Optionally, read initial debug bytes (if any) as in your original code
    numBytes = 0;
    err = LJM_eReadName(handle, "LUA_DEBUG_NUM_BYTES", &numBytes);
    ErrorCheck(err, "LJM_eReadName(%d, LUA_DEBUG_NUM_BYTES, ...)", handle);
    if ((int)numBytes != 0) {
        const char *searchString = "2D Voltage Scan Completed.";
        aBytes = malloc(sizeof(char) * (int)numBytes);
        errorAddress = INITIAL_ERR_ADDRESS;
        err = LJM_eReadNameByteArray(
            handle,
            "LUA_DEBUG_DATA",
            numBytes,
            aBytes,
            &errorAddress
        );
        // You might process these bytes if necessary.
        free(aBytes);
    }

    // Write scan parameters to registers
    LJM_eWriteName(handle, "USER_RAM0_F32", x_start);  // X start voltage
    LJM_eWriteName(handle, "USER_RAM1_F32", y_start);  // Y start voltage
    LJM_eWriteName(handle, "USER_RAM2_F32", x_end);    // X end voltage
    LJM_eWriteName(handle, "USER_RAM3_F32", y_end);    // Y end voltage
    LJM_eWriteName(handle, "USER_RAM0_U16", steps);    // Number of steps
    LJM_eWriteName(handle, "USER_RAM4_F32", dwell);    // Dwell time (ms)
    LJM_eWriteName(handle, "USER_RAM2_U16", 1);        // Set Flag to 1 to run the scan

    ReadLuaInfo(handle);
    CloseOrDie(handle);
    return LJME_NOERROR;
}

void ReadLuaInfo(int handle)
{
    int byteIter, err;
    double numBytes;
    char *aBytes;
    int errorAddress;

    // Open file for writing
    FILE *fp = fopen("lua_output.txt", "w");
    if (fp == NULL) {
        perror("Failed to open file");
        return;
    }

    // Record the time when the last data was received.
    time_t lastDataTime = time(NULL);

    while (true) {
        // Optional: add a short sleep to reduce CPU usage (e.g., 100 milliseconds)
        // struct timespec req = {0, 100 * 1000000};  // 100 milliseconds
        // nanosleep(&req, NULL);

        numBytes = 0;
        err = LJM_eReadName(handle, "LUA_DEBUG_NUM_BYTES", &numBytes);
        ErrorCheck(err, "LJM_eReadName(%d, LUA_DEBUG_NUM_BYTES, ...)", handle);

        if ((int)numBytes == 0) {
            // If no new data is received for longer than 5 seconds, exit the loop.
            if (difftime(time(NULL), lastDataTime) > 10.0) {
                LJM_eWriteAddress(handle,61998,1,1279918080);
                fprintf(stderr, "Timeout: No data received for 5 seconds. Exiting.\n");
                break;
            }
            continue;
        } else {
            // Data has been received; update the lastDataTime.
            lastDataTime = time(NULL);
        }

        const char *searchString = "2D Voltage Scan Completed.";
        aBytes = malloc(sizeof(char) * (int)numBytes);
        errorAddress = INITIAL_ERR_ADDRESS;
        err = LJM_eReadNameByteArray(
            handle,
            "LUA_DEBUG_DATA",
            numBytes,
            aBytes,
            &errorAddress
        );
        if (err == LJME_NOERROR) {
            for (byteIter = 0; byteIter < numBytes; byteIter++) {
                fputc(aBytes[byteIter], fp);    // Write to file
                // printf("%c", aBytes[byteIter]);  // still print to console (optional)

            }
            // Optionally print to console:
            // printf("%s", aBytes);
            if (strstr(aBytes, searchString) != NULL) {
                free(aBytes);
                break;
            }
        }
        free(aBytes);
        ErrorCheck(err, "LJM_eReadNameByteArray(%d, LUA_DEBUG_DATA, ...", handle);
    }
    fclose(fp);  // Close the file
}
