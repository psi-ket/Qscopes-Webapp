#include <stdbool.h>
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
#else
    #include <arpa/inet.h>  // For inet_ntoa()
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#include <LabJackM.h>
#include "LJM_Utilities.h"

#define NUM_TOTAL_ROWS 100
#define NUM_VALUES_PER_LINE 50
#define NUM_CHUNK_LINES 100/50
#define NUM_VALUES_PER_ROW (NUM_CHUNK_LINES * NUM_VALUES_PER_LINE)

static void ParseAndPlotHeatmap(const char *inFilename);
void ReadLuaInfo(int handle);

int main()
{
    bool isActive = true;
    int handle;
    handle = OpenOrDie(LJM_dtANY, LJM_ctANY, "LJM_idANY");

    LJM_eWriteName(handle, "USER_RAM4_F32", 1);
    LJM_eWriteName(handle, "USER_RAM2_U16", 1);

    clock_t start_time, end_time;
    double elapsed_time;

    start_time = clock();
    ReadLuaInfo(handle);
    end_time = clock();

    elapsed_time = ((double)(end_time - start_time)) / CLOCKS_PER_SEC;
    printf("ReadLuaInfo took %.3f seconds\n", elapsed_time);

    CloseOrDie(handle);

    // After we've broken out of ReadLuaInfo(), we can parse lua_output.txt
    // and attempt to construct the 100x100 data set. Then plot it.
    // (If not enough lines were generated, the parse step will fail.)
    ParseAndPlotHeatmap("lua_output.txt");

    WaitForUserIfWindows();
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
        perror("Failed to open file lua_output.txt");
        return;
    }

    const char *searchString = "2D Voltage Scan Completed.";
    
    while (true) {
        MillisecondSleep(1);

        numBytes = 0;
        err = LJM_eReadName(handle, "LUA_DEBUG_NUM_BYTES", &numBytes);
        ErrorCheck(err, "LJM_eReadName(%d, LUA_DEBUG_NUM_BYTES, ...)", handle);

        if ((int)numBytes == 0) {
            continue;
        }

        // Allocate enough space + 1 byte for safe NULL termination
        aBytes = (char *)malloc(sizeof(char) * ((int)numBytes + 1));
        if (aBytes == NULL) {
            perror("Failed to allocate memory for aBytes");
            fclose(fp);
            return;
        }

        errorAddress = INITIAL_ERR_ADDRESS;
        err = LJM_eReadNameByteArray(
            handle,
            "LUA_DEBUG_DATA",
            (int)numBytes,
            aBytes,
            &errorAddress
        );
        if (err == LJME_NOERROR) {
            // Null-terminate so we can safely use strstr
            aBytes[(int)numBytes] = '\0';

            // Write to file & print to console
            for (byteIter = 0; byteIter < numBytes; byteIter++) {
                fputc(aBytes[byteIter], fp);
                printf("%c", aBytes[byteIter]);
            }
            printf("\n");

            // Check for the "2D Voltage Scan Completed." message
            if (strstr(aBytes, searchString) != NULL) {
                printf("Found \"%s\". Breaking out of loop.\n", searchString);
                free(aBytes);
                break;
            }
        }

        free(aBytes);
        ErrorCheck(err, "LJM_eReadNameByteArray(%d, LUA_DEBUG_DATA, ...", handle);
    }

    fclose(fp);  // close the file
}

/**
 * Attempts to parse 400 lines of data from inFilename in 4×25 chunks
 * to build a 100×100 float matrix, then writes it to heatmap.csv,
 * and plots with Gnuplot to heatmap.png.
 */
static void ParseAndPlotHeatmap(const char *inFilename)
{
    // We'll read the file into an internal 2D array [100][100]
    float data[NUM_TOTAL_ROWS][NUM_VALUES_PER_ROW];

    FILE *fp = fopen(inFilename, "r");
    if (fp == NULL) {
        perror("Failed to open lua_output.txt for parsing");
        return;
    }

    // Because your LUA output might contain extra prints, or fewer lines,
    // we need to parse carefully. We'll try to read 400 lines exactly.
    // Each group of 4 lines => 1 row of 100 floats in our matrix.

    char line[1024];
    int rowIndex = 0;
    while (rowIndex < NUM_TOTAL_ROWS) {
        float rowValues[NUM_VALUES_PER_ROW];
        memset(rowValues, 0, sizeof(rowValues));

        // Each row is comprised of 4 lines
        for (int chunkLine = 0; chunkLine < NUM_CHUNK_LINES; chunkLine++) {
            if (!fgets(line, sizeof(line), fp)) {
                // We have fewer lines than expected
                fprintf(stderr, "Error: Reached EOF or failed read at row %d, chunkLine %d.\n", rowIndex, chunkLine);
                fclose(fp);
                return;
            }

            // Skip empty lines
            if (strlen(line) < 2) {
                // re-try the read for this chunk line
                chunkLine--;
                continue;
            }

            // Parse 25 floats from the line
            float vals[NUM_VALUES_PER_LINE];
            int count = 0;
            char *token = strtok(line, " \t\r\n");
            while (token && count < NUM_VALUES_PER_LINE) {
                vals[count++] = (float)atof(token);
                token = strtok(NULL, " \t\r\n");
            }

            if (count < NUM_VALUES_PER_LINE) {
                fprintf(stderr, "Error: Found only %d floats instead of 50 on line\n", count);
                fclose(fp);
                return;
            }

            // Copy these 25 floats into the correct location in rowValues
            memcpy(&rowValues[chunkLine * NUM_VALUES_PER_LINE], vals, sizeof(float) * NUM_VALUES_PER_LINE);
        }

        // Now we have a full 100 floats for rowIndex
        memcpy(data[rowIndex], rowValues, sizeof(rowValues));
        rowIndex++;
    }

    fclose(fp);

    // We have a 100×100 array in 'data'.
    // Let's write it to heatmap.csv in matrix form.
    FILE *csv = fopen("heatmap.csv", "w");
    if (!csv) {
        perror("Failed to open heatmap.csv for writing");
        return;
    }
    for (int r = 0; r < NUM_TOTAL_ROWS; r++) {
        for (int c = 0; c < NUM_VALUES_PER_ROW; c++) {
            fprintf(csv, "%f", data[r][c]);
            if (c < (NUM_VALUES_PER_ROW - 1)) {
                fputc(',', csv);
            }
        }
        fputc('\n', csv);
    }
    fclose(csv);
    printf("Wrote 100×100 data to heatmap.csv\n");

    // Now let's create a quick Gnuplot script to turn that CSV file into a heatmap image.
    // We'll output "heatmap.png"
    FILE *gp = fopen("plot.gp", "w");
    if (!gp) {
        perror("Failed to open plot.gp for writing");
        return;
    }

    fprintf(gp,
        "set terminal pngcairo size 800,600\n"
        "set output 'heatmap.png'\n"
        // We treat the CSV as a matrix with 100 columns
        // `using 1:2:3` is not needed if we use 'matrix' style
        "set view map\n"
        "set datafile separator comma\n"
        "set xtics rotate by -45\n"
        "set yrange [0:*] reverse\n"    // so row 0 is at top
        "set cblabel 'Value'\n"
        "plot 'heatmap.csv' matrix with image\n"
        "set output\n"
    );
    fclose(gp);

    // Finally, call Gnuplot (if available on this system).
    // This will produce "heatmap.png" in the current directory.
    int ret = system("gnuplot plot.gp");
    if (ret == -1) {
        fprintf(stderr, "Could not invoke gnuplot. Is it installed?\n");
    } else {
        printf("Gnuplot script completed. Check 'heatmap.png' for the plot.\n");
    }
}
