function scan_voltages(x_start, y_start, x_end, y_end, steps, dwell)
    -- Validate input parameters
    local count = 0
    local modbus_read = MB.R
    local modbus_write = MB.W
    local i = 0

    if steps < 2 then
        print("Error: 'steps' must be at least 2.")
        return
    end

    -- Calculate the voltage increment for each step
    local x_step = (x_end - x_start) / (steps - 1)
    local y_step = (y_end - y_start) / (steps - 1)
    
    -- Define the core ticks per second.
    -- For a T-series device with an 80 MHz core clock, the tick counter runs at 80MHz/2 = 40MHz.
    local coreTicksPerSecond = 40000000
    -- Calculate ticks per millisecond.
    local ticksPerMs = coreTicksPerSecond / 1000  -- 40000 ticks per ms

    for y = 0, steps - 1 do
        local current_y = y_start + (y_step * y)
        current_y = math.max(-5, math.min(current_y, 5))
        modbus_write(30000, 3, current_y)
        local row_counts = {0}
        for x = 0, steps - 1 do
            local current_x = x_start + (x_step * x)
            current_x = math.max(-5, math.min(current_x, 5))
            modbus_write(30002, 3, current_x)
            i = i + 1

            -- Flush a read to clear any buffered value (optional)
            modbus_read(3136, 1)
            
            -- Start dwell timing using core ticks
            local start_tick = LJ.Tick()
            local dwell_ticks = dwell * ticksPerMs   -- dwell is now in ms
            -- modbus_read(3136, 1)  -- Optional flush read before timing dwell
            while (LJ.Tick() - start_tick) < dwell_ticks do
                -- Waiting for the dwell period in ms to pass
            end
            
            -- After the dwell period, read the counter value
            count = modbus_read(3136, 1)
            table.insert(row_counts, count)
            
            if i == 25 then
                print(table.concat(row_counts, " "))
                row_counts = {0}
                i = 0
            end
            -- -- Wait for the condition on reading 6022 to be met before continuing
            while modbus_read(6022, 1) > 8700 do
                -- Do nothing while condition holds
            end
        end
        row_counts = {0}
    end
    print("2D Voltage Scan Completed.")
    modbus_write(30002, 3, 0)
    modbus_write(30000, 3, 0)
end

-- Throttle setting based on a rule of thumb: Throttle = (3 * NumLinesCode) + 20
ThrottleSetting = 278

LJ.setLuaThrottle(ThrottleSetting)
local modbus_write = MB.W

-- Enable CounterA on DIO16/CIO0
modbus_write(44036, 1, 0)
-- Write 7 to DIO16_EF_INDEX (using the high-speed counter feature)
modbus_write(44136, 1, 7)
-- Re-enable DIO16
modbus_write(44036, 1, 1)

local startx, starty, stopx, stopy, step, intT = 0, 0, 0, 0, 0, 0
MB.writeName("USER_RAM0_F32", 0.3)   -- Start amp x
MB.writeName("USER_RAM1_F32", 0.3)   -- Start amp y
MB.writeName("USER_RAM2_F32", -0.3)  -- End amp x
MB.writeName("USER_RAM3_F32", -0.3)  -- End amp y
MB.writeName("USER_RAM0_U16", 100)    -- Step count
MB.writeName("USER_RAM4_F32", 1)      -- Dwell time in ms (set this value accordingly)
MB.writeName("USER_RAM2_U16", 0)      -- Set Flag to trigger scan

while true do
    if MB.readName("USER_RAM2_U16") == 1 then
        startx = MB.readName("USER_RAM0_F32")
        starty = MB.readName("USER_RAM1_F32")
        stopx = MB.readName("USER_RAM2_F32")
        stopy = MB.readName("USER_RAM3_F32")
        step = MB.readName("USER_RAM0_U16")
        intT = MB.readName("USER_RAM4_F32")
        scan_voltages(startx, starty, stopx, stopy, step, intT)
        MB.writeName("USER_RAM2_U16", 0)  -- Reset trigger
    end
end