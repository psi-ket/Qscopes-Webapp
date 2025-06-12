#include <stdbool.h>
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h> // For inet_ntoa()
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
// #include <time.h>

#include <LabJackM.h>
#include "LJM_Utilities.h"

void ReadLuaInfo(int handle);

int main()
{
	bool isActive = true;
	int handle;
	// Open first found LabJack
	handle = OpenOrDie(LJM_dtANY, LJM_ctANY, "LJM_idANY");
	PrintDeviceInfoFromHandle(handle);
	GetAndPrint(handle, "FIRMWARE_VERSION");
	printf("\n");

	GetAndPrint(handle, "LUA_RUN");
	GetAndPrint(handle, "LUA_DEBUG_NUM_BYTES");
	LJM_eWriteName(handle, "USER_RAM4_F32", 1);
	LJM_eWriteName(handle, "USER_RAM2_U16", 1);
	// clock_t start_time, end_time;
	// double elapsed_time;

	// start_time = clock();
	ReadLuaInfo(handle);
	// end_time = clock();

	// elapsed_time = ((double)(end_time - start_time)) / CLOCKS_PER_SEC;
	// printf("ReadLuaInfo took %.3f seconds\n", elapsed_time);

	CloseOrDie(handle);

	WaitForUserIfWindows();

	return LJME_NOERROR;
}

void ReadLuaInfo(int handle)
{
	int i, byteIter, err;
	double numBytes;
	char *aBytes;
	int errorAddress;
	while (true)
	{
		MillisecondSleep(25);
		numBytes = 0;
		err = LJM_eReadName(handle, "LUA_DEBUG_NUM_BYTES", &numBytes);
		ErrorCheck(err, "LJM_eReadName(%d, LUA_DEBUG_NUM_BYTES, ...)", handle);

		if ((int)numBytes == 0)
		{
			continue;
		}
		aBytes = malloc(sizeof(char) * (int)numBytes);
		errorAddress = INITIAL_ERR_ADDRESS;
		err = LJM_eReadNameByteArray(
			handle,
			"LUA_DEBUG_DATA",
			numBytes,
			aBytes,
			&errorAddress);
		if (err == LJME_NOERROR)
		{
			for (byteIter = 0; byteIter < numBytes; byteIter++)
			{
				printf("%c", aBytes[byteIter]);
			}
			printf("\n");
		}
		free(aBytes);
		ErrorCheck(err, "LJM_eReadNameByteArray(%d, LUA_DEBUG_DATA, ...", handle);
	}
}
