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

void LoadLuaScript(int handle, const char * luaScript);

void ReadLuaInfo(int handle);

int main()
{
	bool isActive = true;
	int handle;
	handle = OpenOrDie(LJM_dtT7, 0, "LJM_idANY");

	PrintDeviceInfoFromHandle(handle);  
	LJM_eWriteName(handle,"USER_RAM0_F32",-0.5);     // X start voltage
	LJM_eWriteName(handle,"USER_RAM1_F32",-0.5);     // Y start voltage
	LJM_eWriteName(handle,"USER_RAM2_F32",0.5);       // X end voltage
	LJM_eWriteName(handle,"USER_RAM3_F32",0.5);       // Y end voltage
	LJM_eWriteName(handle,"USER_RAM0_U16",100);       // Number of steps
	LJM_eWriteName(handle,"USER_RAM4_F32",1);       // Dwell time (ms)
	LJM_eWriteName(handle,"USER_RAM2_U16",1);           // Set Flag to 1 to run the scan
	clock_t start_time, end_time;
	double elapsed_time;
	
	start_time = clock();
	ReadLuaInfo(handle);
	end_time = clock();
	
	elapsed_time = ((double)(end_time - start_time)) / CLOCKS_PER_SEC;
	printf("ReadLuaInfo took %.3f seconds\n", elapsed_time);
	
	CloseOrDie(handle);
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
		perror("Failed to open file");
		return;
	}

	while (true) {
		MillisecondSleep(0.5);
		numBytes = 0;
		err = LJM_eReadName(handle, "LUA_DEBUG_NUM_BYTES", &numBytes);
		ErrorCheck(err, "LJM_eReadName(%d, LUA_DEBUG_NUM_BYTES, ...)", handle);

		if ((int)numBytes == 0) {
			continue;
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
				fputc(aBytes[byteIter], fp);     // write to file
				printf("%c", aBytes[byteIter]);  // still print to console (optional)
			}
			printf("\n");
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
